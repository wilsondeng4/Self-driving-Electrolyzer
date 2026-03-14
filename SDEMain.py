""" MAKE SURE H2O in the syringe to 10 mL when you run the code"""

#import standard libraries
import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import time
from datetime import datetime
import threading

#import BO related libraries
import torch
from torch import Tensor
from botorch.models import SingleTaskGP
from gpytorch.mlls import ExactMarginalLogLikelihood
from botorch.fit import fit_gpytorch_mll
from scipy.stats import norm
from botorch.acquisition.analytic import LogExpectedImprovement, UpperConfidenceBound
from botorch.models.transforms.outcome import Standardize
# from botorch.models.transforms.input import Normalize

#import from hardware scripts
from ni_controller import NIUSB621xController
from spec_sensor import SPECSensor
from sensirion_mfc import SFC5xxxMFC
from psd6_pumps_25mL import PSD6Pumps
from NewEraPump import NewEraPump
from NewPeriPump import PeriPump


TORCH_DTYPE = torch.double

# ===============
# ILR (tempered)
# ===============
_ILR_BASIS = torch.tensor([
    [ 1.0/2**0.5,   1.0/6**0.5,   1.0/12**0.5],
    [-1.0/2**0.5,   1.0/6**0.5,   1.0/12**0.5],
    [ 0.0,         -2.0/6**0.5,   1.0/12**0.5],
    [ 0.0,          0.0,         -3.0/12**0.5],
], dtype=TORCH_DTYPE)

def ilr_from_unit_simplex_tempered(X01: Tensor, tau: float = 0.1) -> Tensor:
    B = _ILR_BASIS.to(device=X01.device, dtype=X01.dtype)
    X_tau = X01 + tau   # pseudo-count
    logX  = torch.log(X_tau)
    
    clr   = logX - logX.mean(dim=-1, keepdim=True)
    return clr @ B  # (...,3)

def make_tr_box(center: torch.Tensor, length: float, lengthscales: torch.Tensor | None):
    if lengthscales is None:
        scale = torch.ones(3, dtype=center.dtype, device=center.device)
    else:
        ls = lengthscales.reshape(-1)
        scale = (ls / ls.mean()).clamp(0.25, 4.0)
    half = 0.5 * length * scale
    lb = (center - half).clamp(0.0, 1.0)
    ub = (center + half).clamp(0.0, 1.0)
    return lb, ub

def filter_in_box(Z01_all: torch.Tensor, lb: torch.Tensor, ub: torch.Tensor, mask_unobs: torch.Tensor):
    in_box = (Z01_all >= lb) & (Z01_all <= ub)
    return torch.where(in_box.all(dim=-1) & mask_unobs)[0]

# Acquisition helpers (BoTorch built-ins)
@torch.no_grad()
def acq_ucb(model, X01, beta: float):
    Xq = X01.unsqueeze(-2)
    return UpperConfidenceBound(model=model, beta=beta)(Xq).squeeze(-1)

@torch.no_grad()
def acq_logei(model, X01, best_f: float):
    Xq = X01.unsqueeze(-2)
    return LogExpectedImprovement(model=model, best_f=best_f)(Xq).squeeze(-1)


# Convert sensor signal to FE
'''
MODIFY THIS FUNCTION
'''
def sensor_to_FE(sensor):
    slope = 0.0194
    intercept = -5.3574
    return slope*sensor + intercept


# refill function for DI water
def refill_DI(DI_pump):
    DI_pump.set_flowrate(10)
    DI_pump.refill()
    time.sleep(218)   # Nov 04 
    DI_pump.stop()

class SDE:
    def __init__(self, verbose=True):
        self.sensor = SPECSensor()
        self.psd6_pumps = PSD6Pumps(verbose=True)       # 0: DI/Air, 1/2: Electrolytes - Apr 04
        self.DAQ = NIUSB621xController()
        self.MFC_CO2 = SFC5xxxMFC()
        self.MFC_Air = SFC5xxxMFC(portname = 'COM12', gas_type = 0)
        self.Sample = PeriPump()
        self.DI_pump = NewEraPump()

        self.VERBOSE = verbose
        self.BUFFERLEN = 100 # INTERVAL x BUFFERLEN in seconds
        self.INTERVAL = 1.0
        self.sensorBuffer = np.zeros(self.BUFFERLEN)
        self.voltageBuffer = np.zeros(self.BUFFERLEN)
        self.timeBuffer =  np.zeros(self.BUFFERLEN)
        self.tempBuffer = np.zeros(self.BUFFERLEN)
        self.rhBuffer = np.zeros(self.BUFFERLEN)

        #constructing meta data_data frame
        self.metaData_df = pd.DataFrame({
                "Time":[0],
                "Voltage":[0],
                "Sensor":[0],
                "Temperature":[0],
                "RH": [0],
            })
        
        #constructing result data frame
        self.result_df = pd.DataFrame({
                "K":[0],
                "Na":[0],
                "Cs":[0],
                "Li":[0],
                "Time":[0],
                "Sensor":[0],
                "Voltage":[0]
            })
            
        #Initializing CO2 flow to 30 sccm
        self.MFC_CO2.connect()
        self.MFC_CO2.set_flowrate(30)

        self.MFC_Air.connect()
        self.MFC_Air.set_flowrate(1970)

        #Initializing DAQ
        #reset power to off state
        self.DAQ.analogWrite(0)

        #Dummy code to activate the connection with DI pump
        self.DI_pump.set_flowrate(0) #activate the com port
        self.DI_pump.set_flowrate(1) #sanity check, make sure LCD displays 1

        #Initializing PSD6 syringe 
        self.psd6_pumps.initialize() # Blocking operation
        self.psd6_pumps.refill() # Non-blocking operation
        time.sleep(50)
        self.psd6_pumps.stop_pumps()

        #initializing plotting
        plt.ion()  # Turn on interactive mode
        self.fig, self.ax1 = plt.subplots()
        self.ax2 = self.ax1.twinx()
        self.scatter1 = self.ax1.scatter(self.timeBuffer, self.sensorBuffer, label = 'PPB', color='b')
        self.scatter2 = self.ax2.scatter(self.timeBuffer, self.voltageBuffer, label = 'Voltage', color='r')
        self.ax1.set_xlabel('Time (s)')
        self.ax1.set_ylabel('PPB')
        self.ax1.set_title('PPB vs. Time')
        self.ax2.set_ylabel('V')
        plt.legend()

        self.startTime = time.monotonic() # Change time.time() to time.monotonic() - Apr 03

    def livePlot(self, duration):
        #substitution for np.roll, because Lee doesn't like it :(
        def my_roll(arr, x):
            arr[:-1] = arr[1:]
            arr[-1] = x
            return arr

        tempTime = time.monotonic() #set a timer
        while ((time.monotonic() - tempTime) <= duration): #set the duration of the plot and data acquisition
            if self.VERBOSE:
                print(f"{(duration - (time.monotonic() - tempTime)):.1f}s left for this iteration")
            
            #appending data first:
            sensorData = self.sensor.read()
            self.sensorBuffer = my_roll(self.sensorBuffer, sensorData[0])
            self.tempBuffer = my_roll(self.tempBuffer, sensorData[1])
            self.rhBuffer = my_roll(self.rhBuffer, sensorData[2]) # Wow, this is bad
            self.voltageBuffer = my_roll(self.voltageBuffer, self.DAQ.analogRead())
            self.timeBuffer = my_roll(self.timeBuffer, (time.monotonic() - self.startTime))

            newData = pd.DataFrame([
                {
                'Time': self.timeBuffer[-1],
                'Voltage': self.voltageBuffer[-1],
                'Sensor': self.sensorBuffer[-1],
                'Temperature': self.tempBuffer[-1],
                'RH': self.rhBuffer[-1]
                }
            ])
            self.metaData_df = pd.concat([self.metaData_df, newData], ignore_index=True) #add data to the last row of the data frame
            #plotting
            # Update scatter plot with new data
            self.scatter1.set_offsets(np.c_[self.timeBuffer, self.sensorBuffer])
            self.scatter2.set_offsets(np.c_[self.timeBuffer, self.voltageBuffer])
        
            # adjust the scale dynamically
            self.ax1.set_xlim(self.timeBuffer[0], self.timeBuffer[-1])
            self.ax1.set_ylim(min(self.sensorBuffer) - 1000, max(self.sensorBuffer) + 1000)
            self.ax2.set_ylim(min(self.voltageBuffer) - 0.5, max(self.voltageBuffer) + 0.5)

            #pause and delay for data acquisition
            self.MFC_CO2.read_flow()
            self.MFC_Air.read_flow()
            plt.pause(0.01)
            time.sleep(self.INTERVAL)

    def cleaning(self):
        #Turn off power
        self.DAQ.analogWrite(0)

        #Increase air flowrate to purge the sensor chamber
        # self.MFC_Air.set_flowrate(1970)

        # Refill the electrolytes
        self.psd6_pumps.refill([0, 1, 2, 3])

        #Empty remaining liquid in the resorvior
        # self.Sample.set_flowrate_25_start()
        self.Sample.set_flowrate_17_start()
        time.sleep(15) 

        """DI water cycle 20mL"""
        self.DI_pump.set_flowrate(100)
        self.DI_pump.dispense()
        time.sleep(12)
        self.DI_pump.stop()

        #flushing the cell with DI water
        time.sleep(95)

        """DI water cycle 20mL"""
        self.DI_pump.dispense()
        time.sleep(9)
        self.DI_pump.stop()

        #flushing the cell with DI water
        time.sleep(95)
        self.Sample.stop()

    def saveData(self, name = 'BO_metadata'):
        #concat the result_df and metaData_df together
        metaData_result_df = pd.concat([self.metaData_df, self.result_df], axis = 1)
        #save self.df to csv
        now = datetime.now().strftime('%Y-%m-%d %H-%M-%S')
        file_path = f'./data/{name} {now}.csv'
        # file_path = f'./BO/BONew/{name} {now}.csv'
        metaData_result_df.to_csv(file_path, index=False) #save to CSV file


    def runCell(self, channels:list, flowrates:list | float | int, duration:int = 300, isInitial:bool = False):
        if isinstance(flowrates, (float, int)):
            flowrates = [round(flowrates)]      

        # No longer using the method 'activation'
        if isInitial:
            SensorData = self.sensor.read()
            background_noise = SensorData[0]

            #Turn on power
            self.DAQ.analogWrite(5)
        else:
            #Turn off power
            self.DAQ.analogWrite(0)
            # self.MFC_Air.set_flowrate(1500)

        # refill the DI water simultaneously with liveplotting
        thread_refill = threading.Thread(target=refill_DI, args=(self.DI_pump,))
        thread_refill.start()

        # Let the blends go into the cell while formulating
        self.Sample.set_flowrate_25_start()

        #Set flow rate and turn on the electrolytes
        #Formulation around 20 mL        
        self.psd6_pumps.dispense(channels, [flowrate for flowrate in flowrates])

        #refill takes 21 seconds in total
        time.sleep(20)

        # Stop syringe pump and DI pump
        self.psd6_pumps.stop_pumps(channels) #executing this command takes 1 second
        
        # Filling the cell channels
        time.sleep(14) # Oct 21 - increase from 11 to 14

        #Set the airflorate back
        # self.MFC_Air.set_flowrate(970)

        if not isInitial:
            SensorData = self.sensor.read()
            background_noise = SensorData[0]

            #Turn on power supply
            self.DAQ.analogWrite(5)

        self.Sample.set_flowrate_1_start() #set sample pump back to low flowrate

        #Start plotting for a specified duration
        self.livePlot(duration)
        thread_refill.join()

        #Save result data
        resultData = pd.DataFrame({
                "K":[flowrates[channels.index(0)]/5 if 0 in channels else 0],
                "Na":[flowrates[channels.index(1)]/5 if 1 in channels else 0],
                "Cs":[flowrates[channels.index(2)]/5 if 2 in channels else 0],
                "Li":[flowrates[channels.index(3)]/5 if 3 in channels else 0],
                "Time":[self.timeBuffer[-1]],
                "Sensor":[np.mean(self.sensorBuffer[-5:]) - background_noise],
                "Voltage":[np.mean(self.voltageBuffer[-5:])]
            })
        self.result_df = pd.concat([self.result_df, resultData], ignore_index=True)

        #Turn off power supply
        self.DAQ.analogWrite(0)

        self.Sample.stop()


    def runcell_sequence(self, csv_path: str, first_is_initial: bool = True):
        """
        Run a sequence from CSV (columns: K, Na, Cs, Li).
        """

        df = pd.read_csv(csv_path)
        required = ["K", "Na", "Cs", "Li"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"CSV missing columns: {missing}. Required: {required}")

        comp_to_ch = {"K": 0, "Na": 1, "Cs": 2, "Li": 3}

        def composition_to_channels_and_flows(row: pd.Series):
            vals = {c: int(row[c]) for c in required}
            s = sum(vals.values())
            if s != 100:
                raise ValueError(f"Row sum must be 100, got {s}: {row.to_dict()}")
            if any(v < 0 for v in vals.values()):
                raise ValueError(f"All values must be nonnegative integers: {row.to_dict()}")

            channels, flows = [], []
            for c in required:
                v = vals[c]
                if v == 0:
                    continue
                channels.append(comp_to_ch[c])
                flows.append(5 * v)  # total = 500 guaranteed

            if not channels:
                raise ValueError("At least one component must be > 0.")
            return channels, flows

        n = len(df)
        for idx, row in df.iterrows():
            channels, flows = composition_to_channels_and_flows(row)
            is_init = (idx == 0 and first_is_initial)

            # print(f"[runcell_sequence] {idx+1}/{n}  comp=({int(row['K'])},{int(row['Na'])},{int(row['Cs'])},{int(row['Li'])})  "
            #     f"channels={channels}  flows={flows}  isInitial={is_init}")
            # print(f'Performing runcell({channels}, {flows})')
            # time.sleep(2)
            # run the experiment            
            self.runCell(channels, flows, isInitial=is_init)
            self.cleaning()


    def bo_run(self, 
               nb_iterations: int, 
               df_initial: pd.DataFrame, 
               noise_ratio: float = 0.05,
               tau_tempered: float = 0.1,
               restart_warmups: int = 5,
               validation_required: bool=True,
               log_csv_path: str | None = None,
               ):
        

        """
        TuRBO-1 (Top-1) with tempered-ILR and anisotropic trust region.
        - Uses UpperConfidenceBound for warmup, then LogExpectedImprovement.
        - No BoTorch Normalize: inputs are pre-normalized to [0,1]^3 here.
        - Saves per-iteration state logs to CSV if log_csv_path is provided.
        """
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        TORCH_DTYPE = torch.double

        # -------------------------
        # 0) Read sample space
        # -------------------------
        df = pd.read_csv("./sample_space.csv")
        df["mixture_id"] = df[["K","Na","Cs","Li"]].astype(int).apply(lambda r: tuple(r), axis=1)
        df_initial["mixture_id"] = df_initial[["K","Na","Cs","Li"]].astype(int).apply(lambda r: tuple(r), axis=1)
        lookup = {v: i for i, v in df["mixture_id"].items()}
        ids_mapped = df_initial['mixture_id'].map(lookup)
        assert ids_mapped.notna().all(), "Error found in mixture_id rows"
        ids_acquired = ids_mapped.astype(int).to_numpy()
        df.loc[ids_acquired, "FE"] = df_initial["FE"].values

        # tensors
        X = torch.from_numpy(df[["K","Na","Cs","Li"]].astype("float64").values / 100.0).to(device=device, dtype=TORCH_DTYPE)  # (N,4)
        y_all = torch.from_numpy(df["FE"].fillna(np.nan).values).to(device=device, dtype=TORCH_DTYPE).unsqueeze(-1)           # (N,1)

        # -------------------------
        # 1) X -> Z = ILR_tempered(X) -> [0,1]^3
        # -------------------------
        Z_all = ilr_from_unit_simplex_tempered(X, tau=tau_tempered)  # (N,3)
        mins = Z_all.min(dim=0).values
        maxs = Z_all.max(dim=0).values
        Z01_all = (Z_all - mins) / (maxs - mins)                      # (N,3) in [0,1]^3

        # -------------------------
        # 2) Observed/initial sets
        # -------------------------
        N = X.shape[0]
        observed = torch.zeros(N, dtype=torch.bool, device=device)
        observed[torch.as_tensor(ids_acquired, device=device, dtype=torch.long)] = True

        # initial y
        y_init = torch.from_numpy(df_initial["FE"].values).to(device=device, dtype=TORCH_DTYPE).unsqueeze(-1)
        best_id = torch.as_tensor(ids_acquired, device=device)[torch.argmax(y_init)].item()
        best_y  = float(y_init.max().item())

        # -------------------------
        # 3) TuRBO state
        # -------------------------
        state = {
            "center": Z01_all[best_id].clone(),
            "length": 0.8,
            "L_min": 0.5**5,    # 0.5**7
            "L_max": 1.6,
            "s": 0,
            "f": 0,
            "s_tol": 3,         # 5
            "f_tol": 3,         # 4
            "best_y": best_y,
            "warmup_remaining": restart_warmups,
        }

        # logs
        state_rows = []
        
        # -------------------------
        # 4) Main TuRBO loop
        # -------------------------
        for it in range(1, nb_iterations + 1):
            print(f"Iteration number: {it}")
            I_obs = torch.where(observed)[0]
            Xtrain = Z01_all[I_obs]
            ytrain = y_all[I_obs]

            # heteroskedastic fixed noise from ratio
            yvar = torch.clamp((noise_ratio * ytrain).pow(2), min=1e-4)

            # GP (no input Normalize; outcome Standardize OK)
            model = SingleTaskGP(
                Xtrain, ytrain,
                train_Yvar=yvar,
                outcome_transform=Standardize(m=1),
            )
            model.train(); model.likelihood.train()
            
            mll = ExactMarginalLogLikelihood(model.likelihood, model)
            fit_gpytorch_mll(mll)
            
            model.eval(); model.likelihood.eval()

            # lengthscales for anisotropic TR
            try:
                ls = model.covar_module.base_kernel.lengthscale.detach().reshape(-1)
            except Exception:
                ls = None

            lb, ub = make_tr_box(state["center"], state["length"], ls)
            I_tr = filter_in_box(Z01_all, lb, ub, mask_unobs=~observed)

            # if too few → mild expand once
            if I_tr.numel() < 200:
                expand = 0.1 * (ub - lb)
                lb2 = (lb - expand).clamp(0.0, 1.0)
                ub2 = (ub + expand).clamp(0.0, 1.0)
                I_tr = filter_in_box(Z01_all, lb2, ub2, mask_unobs=~observed)

            # still tiny → restart (policy B: jump into a new region)
            ''' MODIFY '''
            # The new center could be the place that has been visited before
            
            if I_tr.numel() < 10:
                state["length"] = 0.8
                state["s"] = state["f"] = 0
                state["warmup_remaining"] = restart_warmups

                subset = torch.randperm(N, device=device)[:min(5000, N)]
                subset = subset[(~observed[subset])]
                if subset.numel() == 0:
                    break
                acq_vals = acq_ucb(model, Z01_all[subset], beta=6.0)
                new_center_id = subset[acq_vals.argmax()]
                state["center"] = Z01_all[new_center_id].clone()

                lb, ub = make_tr_box(state["center"], state["length"], ls)
                I_tr = filter_in_box(Z01_all, lb, ub, mask_unobs=~observed)
                if I_tr.numel() == 0:
                    break

            # UCB warmup → LogEI
            if state["warmup_remaining"] > 0:
                beta = 2.0 + 8.0 * (state["warmup_remaining"] / max(1, restart_warmups))  # 10 to 2
                acq_vals = acq_ucb(model, Z01_all[I_tr], beta=beta)
            else:
                acq_vals = acq_logei(model, Z01_all[I_tr], best_f=state["best_y"])

            # Top-1 
            next_id = I_tr[acq_vals.argmax()].item()

            # X is now in the 3D space
            sample_row = df.loc[next_id, ['K','Na','Cs','Li']]
            sample_to_run = sample_row.astype(int).tolist()

            print('######Running composition:', sample_to_run)
            pump_flowrate = [x * 5 for x in sample_to_run]
            # print('######syringe pump flow rate:', pump_flowrate)
            self.runCell([0,1,2,3], pump_flowrate)
            self.cleaning()

            #Getting the lastest result
            sensor_value = self.result_df['Sensor'].iloc[-1]
            FE = sensor_to_FE(sensor_value)
            print('Sensor value:', sensor_value)
            print('FE:', FE)
           
            # Add the result and update ids_acquired
            df.loc[next_id, 'FE'] = float(FE)
            ids_acquired = np.concatenate((ids_acquired, [next_id])) 
            observed[next_id] = True
            y_all[next_id, 0] = torch.as_tensor(FE, dtype=TORCH_DTYPE, device=device)


            # Success or Fail -> Adjust TR
            improve = FE - state["best_y"]
            thresh = max(1e-3, 0.01 * abs(state["best_y"]))
            if improve > thresh:
                state["s"] += 1; state["f"] = 0; state["best_y"] = FE
                if state["s"] >= state["s_tol"]:
                    state["length"] = min(2.0 * state["length"], state["L_max"])
                    state["s"] = 0
            else:
                state["f"] += 1; state["s"] = 0
                if state["f"] >= state["f_tol"]:
                    state["length"] = 0.5 * state["length"]
                    state["f"] = 0

            state["center"] = Z01_all[next_id].clone()
            if state["warmup_remaining"] > 0:
                state["warmup_remaining"] -= 1

            # collapse -> restart
            if state["length"] < state["L_min"]:
                state["length"] = 0.8
                state["s"] = state["f"] = 0
                state["warmup_remaining"] = restart_warmups
                subset = torch.randperm(N, device=device)[:min(5000, N)]
                subset = subset[(~observed[subset])]
                if subset.numel() > 0:
                    acq_vals = acq_ucb(model, Z01_all[subset], beta=6.0)
                    new_center_id = subset[acq_vals.argmax()]
                    state["center"] = Z01_all[new_center_id].clone()

            # Logging the states
            state_rows.append({
                "iter": it,
                "selected_id": int(next_id),
                "FE": FE,
                "best_y": state["best_y"],
                "length": state["length"],
                "s": state["s"],
                "f": state["f"],
                "warmup_remaining": state["warmup_remaining"],
                "center_z01_x": float(state["center"][0].item()),
                "center_z01_y": float(state["center"][1].item()),
                "center_z01_z": float(state["center"][2].item()),
                "lb_x": float(lb[0].item()), "lb_y": float(lb[1].item()), "lb_z": float(lb[2].item()),
                "ub_x": float(ub[0].item()), "ub_y": float(ub[1].item()), "ub_z": float(ub[2].item()),
            })

            #overwrite the figure everytime.
            plt.close()
            plt.figure()
            plt.plot(df.loc[ids_acquired, 'FE'].values.astype(float), marker='o') 
            # plt.plot(df_y.loc[ids_acquired].values, marker='o') 
            # plt.axhline(y=10, linestyle='--', color='gray')
            plt.title(f'Iteration {it}')
            plt.xlabel('Index')
            plt.ylabel('FE')
            plt.show()
            
            # Validation in 10 cycles
            if validation_required:
                if (it%10 == 0):
                    # print("####### Validation using K")
                    # self.runCell([0], [500])
                    print("####### Validation using Cs")
                    self.runCell([2], [500])
                    self.cleaning()

        # save to csv
        if log_csv_path is not None and len(state_rows) > 0:
            try:
                pd.DataFrame(state_rows).to_csv(log_csv_path, index=False)
            except Exception:
                import csv
                with open(log_csv_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(state_rows[0].keys()))
                    writer.writeheader(); writer.writerows(state_rows)

        return df, ids_acquired


    def campaign_run(self):
        """"K, Na, Cs, Li"""
        """"0, 1, 2, 3"""

        ''' 
        Sensor calibration 
        '''
        # self.runcell_sequence('./sequence/calibration_sequences.csv', first_is_initial=False)

        ''' 
        Activation
        '''
        # self.runcell_sequence('./sequence/activation_sequences.csv', first_is_initial=True)

        '''
        Repeatability
        '''
        # self.runcell_sequence('./sequence/repeatability_sequences.csv', first_is_initial=False)

        '''
        Training data
        '''
        # self.runcell_sequence('./sequence/training_dataset_sequences.csv', first_is_initial=False)

        '''
        actual campaign
        '''
        # df_initial = pd.read_csv('./training_data_50mA_Feb17.csv')
        # df, ids_acquired = self.bo_run(nb_iterations=45, df_initial=df_initial, log_csv_path=r'./data/TuRBO_states.csv')
        # BO_result = df.loc[ids_acquired, ['K','Na','Cs','Li','FE']].reset_index(drop=True)
        # BO_result.to_csv(f"./data/BO_result_50mA {datetime.now().strftime('%Y-%m-%d %H-%M-%S')}.csv", index=False) 

        # self.runcell_sequence('./sequence/validation_sequences.csv', first_is_initial=False)
        '''
        Result validation
        '''
        # this includes activation sequence
        self.runcell_sequence('./sequence/result_validation_sequences.csv', first_is_initial=True)

if __name__ == '__main__':
    try:
        sde = SDE() #initialization
        sde.campaign_run() #running the sequence
        sde.saveData()

        #turning off everything
        sde.DAQ.analogWrite(0)
        sde.psd6_pumps.stop_pumps()
        sde.Sample.stop()
        sde.MFC_Air.set_flowrate(0)
        sde.MFC_CO2.set_flowrate(0)
        sde.DI_pump.stop()
        del sde

    except KeyboardInterrupt:
        sde.saveData()
        sde.DAQ.analogWrite(0)
        sde.psd6_pumps.stop_pumps()
        sde.Sample.stop()
        sde.MFC_Air.set_flowrate(0)
        sde.MFC_CO2.set_flowrate(0)
        sde.DI_pump.stop()
        del sde
