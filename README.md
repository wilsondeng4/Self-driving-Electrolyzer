# Self-driving CO2 electrolyzer for ethylene-selective electrolyte 
Authors: Haoyang Deng, Hyeon Seok Lee, Mahyar Rajabi Kochi, *et al.*

## Directory descriptions

### SDE hardware code

This folder contains all the SDE hardware code
`requirements.txt`: Python libraries needed to run the following SDE codes. Please install with `pip install` in the command window.

`SDEMain.py`: Main code includes other classes. The `campaign_run` method uses `runcell_sequence` and `bo_run` methods to get predefined sequences from the `sequence` directory and perform the TuRBO campaign or other specified sequences.

`NewEraPump.py`: Hardware class of NewEra NE–1,000 syringe pump. This class includes operational methods for the syringe pump using the RS232 communication protocol. The commands are used to handle deionized water delivery and refilling.

`PeriPump.py`: Hardware class of RUNZE fluid LM40A peristaltic pump. This class includes operational methods for the peristaltic pump using the RS485 communication protocol. The commands are used to handle sample and deionized water delivery.

`ni_controller.py`: Hardware class of National Instrument USB6212 data acquisition unit and automated via the National Instrument official library: https://nidaqmx-python.readthedocs.io/en/stable/. The methods are used to monitor MEA cell voltage and control power supply connections with an LCA710 solid-state relay.

`PSD6Pump.py`: Hardware class of Hamilton PSD/6 vertical precision syringe pump. This class includes operational methods for the vertical syringe pump using the RS485 communication protocol. The commands are used to control the unary electrolyte mixing and dispensing.

`sensirion_mfc.py`: Hardware class of Sensirion AG SFC5500 mass flow controller. The automation uses the official Sensirion-supported library: https://sensirion.github.io/python-shdlc-sfc5xxx/index. html.https://sensirion.github.io/python-shdlc-driver/shdlc.html.

`spec_sensor.py`: Hardware class of SPEC sensor DGS2 ethylene gas sensor. This class includes operational methods to monitor gas sensor signals.

`serial_device.py`: Custom-built helper class for checking serial port connections with hardware.


### SDE hardware code/sequence

This folder contains all the sequences used in the `SDEMain.py`

`activation_sequences.csv`: Standard activation sequences used to activate the MEA cell before any follow-up testing.

`calibration_sequences.csv`: Sequences used to calibrate the gas sensor setup. Ran every time before the TuRBO campaign with a separate MEA cell.

`repeatability_sequences.csv`: Sequences used to check SDE repeatability and accuracy. This sequence repeats the four unary electrolytes in the same order 12 times.

`training_dataset_sequences.csv`: Sequences used to gather the initial seed data for the TuRBO campaign. Individual training data is gathered for each TuRBO optimization condition.

`validation_sequences.csv`: Sequences used at the end of training data gathering or TuRBO campaign to validate if the MEA cell and system can return to the benchmark.


### Result data

`SDE raw data.xlsx`: Raw data of different operation conditions. Includes the metadata for the TuRBO campaign and the summarized overall discovered space for each optimized operation condition.

`sample_space.csv`: Overall discovery space, used as an input file for `bo_run` method under `SDEMain.py`.

### Usage
1. Make sure all SDE hardware code is contained in the same folder after installing all the required libraries.
3. Make sure all related hardware has been connected, and correct COMPORTs are set under each hardware class.
4. Make sure the sequence file path and sequence name are correctly entered at `runcell_sequence('./sequence/activation_sequences.csv', first_is_initial=True)` under the `campaign_run` function in `SDEMain.py`. `first_is_initial` sets if the initial experiment in this sequence is the first for a freshly assembled MEA cell. Typically, `first_is_initial=True` for activation_sequences and should be `False` for all other sequences.

## Bayesian Optimization resource used

The Bayesian Optimization algorithm used in `SDEMain.py`'s `bo_run` method uses the BOTorch python package: [https://botorch.org/](https://botorch.readthedocs.io/en/stable/)

The Trust Region Bayesian Optimization (TuRBO) is based on the provided full optimization loop: https://botorch.org/docs/tutorials/turbo_1/
