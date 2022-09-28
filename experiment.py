import numpy as np
import psychtoolbox as ptb
import serial as ser
import itertools
from psychopy import prefs
prefs.general['units'] = 'pix'
prefs.general['fullscr'] = False
prefs.general['allowGUI'] = True
from psychopy import core, data, event, gui, logging, visual

def read_timestamp(serial, nbytes=4, byteorder='little'):
    """
    Reads a timestamp from the specified serial connection. The timestamp is
    assumed to have been sent as an unsigned integer.

    Parameters
    ----------
    serial : serial.Serial
        The serial connection from which to read the timestamp.
    nbytes : int
        The number of bytes to read. Timestamps are generally sent as unsigned 
        longs, so the default is 4.
    byteorder : str
        The endianness of the incoming bytestring. The default is 'little'.

    Returns
    -------
    timestamp : int
        The incoming timestamp interpreted as an integer.

    """
    timestamp = b''
    while len(timestamp) < nbytes:
        if serial.in_waiting > 0:
            timestamp += serial.read()
    timestamp = int.from_bytes(timestamp, byteorder, signed=False)
    return timestamp

###
# INITIALIZATION
###

# Version Numbers:
# 1.0: Pilot 
# 1.05: Pilot with renormalized tones
# 1.1: Full version with audiometry and proper timestamps

# Set constants
experiment_name = 'ITM'  # Experiment name
version_num = '1.1'  # Experiment version number (see above)
serial_port = 'COM6' # 'COM6' on lab Windows, '/dev/cu.usbmodemFA141' on lab iMac
frame_rate = 60  # Set monitor frame rate
score_duration = 2  # Seconds that post-trial score remains onscreen
pretrial_delay = 2  # Seconds of blank screen before each trial
min_fixation = 1  # Minimum duration of fixation cross preceding sync tones
fixation_jitter = .5  # Maximum extra duration of fixation cross before trial
nspr_taps = 30  # Number of taps the SPR task lasts for
nsync_tones = 8  # Number of sync tones on each trial
ncont_tones = 16  # Number of continuation tones on each trial
octaves = [2, 3, 4, 5, 6, 7]  # Octave conditions
iois = [400, 600]  # IOI conditions
conditions = [c for c in itertools.product(octaves, iois)]
practice_ioi = 500  # IOI of practice trials
repetitions_per_block = 2  # Number of repetitions of each octave-IOI pair per block
blocks = 5  # Number of blocks
trials_per_block = len(octaves) * repetitions_per_block  # Number of trials per block

# Randomize trial order. IOI varies across blocks, octave varies across trials
trial_order = []
# Add practice trials (1 per octave at 500 ms IOI)
practice_octaves = np.array(octaves)
np.random.shuffle(practice_octaves)
for octave in practice_octaves:
    trial_order.append({'octave': octave, 'ioi': practice_ioi, 'event': 'practice'})
# Add main trials
for block in range(blocks):
    block_trials = np.array(conditions * repetitions_per_block)
    np.random.shuffle(block_trials)
    for trial in block_trials:
        trial_order.append({'octave': trial[0], 'ioi': trial[1], 'event': 'trial'})

# Set up session info and open dialogue box to enter participant ID
info_dict = dict(
    subject='',
    handedness=''
)
dlg = gui.DlgFromDict(dictionary=info_dict, sortKeys=False, title=experiment_name)
if dlg.OK == False:
    core.quit()
info_dict['experiment'] = experiment_name
info_dict['version'] = version_num

# Set logging
log = logging.LogFile('logs/%s_%s.log' % (experiment_name, info_dict['subject']), level=logging.EXP)
logging.console.setLevel(logging.EXP)

# Set up experiment, trials, window, and text
exp = data.ExperimentHandler(name=experiment_name, version=version_num, 
                             extraInfo=info_dict, 
                             dataFileName='data/%s_%s' % (experiment_name, info_dict['subject']), 
                             savePickle=False, saveWideText=True, 
                             autoLog=True, appendFiles=False)
spr_trial = data.TrialHandler([{}], 1, method='sequential', 
                           dataTypes=['event', 'tap_types', 'tap_times', 'release_times'])
trials = data.TrialHandler(trial_order, 1, method='sequential', 
                           dataTypes=['event', 'octave', 'ioi', 'tone_times', 
                                      'tap_types', 'tap_times', 'release_times'])
exp.addLoop(spr_trial)
exp.addLoop(trials)
win = visual.Window([1280, 1024], screen=0, monitor='Dell 1908FP', color=(-1,-1,-1), fullscr=False)
text = visual.TextStim(win, '', font='Arial', color=(1,1,1), height=72)

###
# ESTABLISH ARDUINO CONNECTION
###

# Prompt to start connection
text.setText('Before we begin, we need to make sure our tapping pad is connected.\nPress SPACEBAR to test the connection')
text.draw()
win.flip()
event.waitKeys(keyList=['space'], clearEvents=True)

# Establish a serial connection with the Arduino and send/receive test messages
text.setText('Testing connection...')
text.draw()
win.flip()
try:
    # Open the serial connection and wait a few seconds for the startup message
    arduino_ser = ser.Serial(serial_port, 9600, timeout=1)
    ptb.WaitSecs(5)
    
    # Read the Arduino's startup message and make sure it includes a ready indicator
    ready = False
    message = None
    all_messages = b''
    while not message == b'':
        message = arduino_ser.readline()
        all_messages += message
        if message == b'Ready!\r\n':
            ready = True
    if not ready:
        raise Exception('Arduino returned the following non-ready message: %s' % all_messages)
    
    # Send an "H" for "Hi" and make sure we receive an "I" response
    arduino_ser.reset_input_buffer()
    arduino_ser.write(b'H')
    for i in range(5):
        ptb.WaitSecs(1)
        if arduino_ser.in_waiting > 0:
            in_byte = arduino_ser.read()
            if in_byte == b'I':
                break
            else:
                raise Exception('Computer received an unexpected response: %s' % in_byte)
    else:
        raise Exception('Computer did not receive a response.')
        
# If the connection fails, print the error message and quit after key press
except Exception as e:
    text.setText('Connection failed with the following message:\n%s' % e)
    text.draw()
    win.flip()
    event.waitKeys(clearEvents=True)
    arduino_ser.close()
    win.close()
    core.quit()

# Prompt to start experiment
text.setText('Connection successful!\nPress SPACEBAR when you are ready to begin.')
text.draw()
win.flip()
event.waitKeys(keyList=['space'], clearEvents=True)

###
# SPR TASK
###

for trial in spr_trial:
    
    # Instructions
    text.setText('Tapping Test')
    text.draw()
    win.flip()
    event.waitKeys(keyList=['space'], clearEvents=True)
    
    # Preparation and pretrial delay
    win.flip()
    pretime = core.StaticPeriod(screenHz=frame_rate, win=win)
    pretime.start(pretrial_delay)
    tap_types = []
    tap_times = []
    release_times = []
    text.setText('+')
    text.draw()
    pretime.complete()
    
    # Signal to the Arduino to begin reading from the FSR; display fixation cross
    arduino_ser.write(b'P')
    win.flip()
    
    # Read tapping info from the Arduino until reaching the target number of taps
    while len(release_times) < nspr_taps:
        if arduino_ser.in_waiting > 0:
            in_byte = arduino_ser.read()
            if in_byte == b'T':
                tap_types.append('P')
                tap_times.append(read_timestamp(arduino_ser))
            elif in_byte == b'R':
                release_times.append(read_timestamp(arduino_ser))
            
    # Signal to the Arduino that the SPR task has ended; blank the screen
    arduino_ser.write(b'I')
    win.flip()
    arduino_ser.reset_input_buffer()  # Clear any extra taps that may have gotten in
    
    # Log data
    spr_trial.addData('event', 'SPR')
    spr_trial.addData('tap_types', tap_types)
    spr_trial.addData('tap_times', tap_times)
    spr_trial.addData('release_times', release_times)
    exp.nextEntry()
    ptb.WaitSecs(pretrial_delay)

###
# MAIN TASK
###

# Instructions
text.setText('Main Task')
text.draw()
win.flip()
event.waitKeys(keyList=['space'], clearEvents=True)
    
# Loop through trials
trial_number = 1  # Start on trial 1
block_number = 0  # Start on block 0 (practice section)
for trial in trials:
    
    ###
    # PRETRIAL
    ###
    
    win.flip()
    trial_start = ptb.GetSecs()

    # Jitter how long before first tone the fixation cross appears (500-1000 ms)
    pretime = core.StaticPeriod(screenHz=frame_rate, win=win)
    pretime.start(pretrial_delay)  # Cross will appear after delay
    pretrial_fixation = min_fixation + np.random.random() * fixation_jitter
    
    # Set octave and IOI for this trial
    octave = trial.octave
    ioi = trial.ioi
    
    # Initialize lists for holding timing data
    tone_times = []
    tap_types = []
    tap_times = []
    release_times = []
    
    # Start fixation cross when tones have loaded and pretrial delay ends
    text.setText('+')
    text.draw()
    pretime.complete()
    win.flip()
    ptb.WaitSecs(pretrial_fixation)

    ###
    # SYNCHRONIZATION-CONTINUATION TAPPING
    ###
    
    # Signal Arduino to begin synchronization-continuation tapping.
    # This hands over control to the Arduino until the trial ends.
    # The message includes B to signal trial beginning, a one-digit integer
    # indicating the octave, and a three-digit integer indicating the IOI.
    # The Arduino is programmed to look for these values after receiving a B.
    arduino_ser.write(b'B%i%i' % (octave, ioi))
    phase = 'B'
    
    # Get tone and tap times by reading messages from the Arduino
    # An "I" message signals an intertrial period, returning control to Python
    while True:
        if arduino_ser.in_waiting > 0:
            in_byte = arduino_ser.read()
            if in_byte in (b'S', b'C'):
                # When the first continuation tone occurs, retroactively mark 
                # the tap that triggered it as type C, since it will have been
                # initially marked as type S
                if in_byte == b'C' and phase != b'C':
                    tap_types[-1] = in_byte.decode('utf-8')
                phase = in_byte.decode('utf-8')
                tone_times.append(read_timestamp(arduino_ser))
            elif in_byte == b'T':
                tap_types.append(phase)
                tap_times.append(read_timestamp(arduino_ser))
            elif in_byte == b'R':
                release_times.append(read_timestamp(arduino_ser))
            elif in_byte == b'I':
                arduino_ser.reset_input_buffer()
                break
    
    # Display score as the standard deviation of continuation tap intervals
    cont_times = np.array(tap_times)[np.array(tap_types) == 'C']
    cont_score = int(np.diff(cont_times).std())
    text.setText('YOUR SCORE IS:\n%i\nTry to keep it as low as possible!' % cont_score)
    text.draw()
    win.flip()
    ptb.WaitSecs(score_duration)
    
    ###
    # POST-TRIAL
    ###
    
    # Save data
    trials.addData('tone_times', tone_times)
    trials.addData('tap_types', tap_types)
    trials.addData('tap_times', tap_times)
    trials.addData('release_times', release_times)
    exp.nextEntry()
    
    ###
    # END OF PRACTICE
    ###
    
    # If this was the final trial of the practice block (0), end the practice
    if block_number == 0 and trial_number == len(octaves):
        text.setText('You have completed the practice run!\nPlease press SPACE when you\'re ready to continue.')
        text.draw()
        win.flip()
        event.waitKeys(keyList=['space'], clearEvents=True)
        block_number += 1
        trial_number = 0
    
    ###
    # POST-BLOCK BREAK
    ### 
    
    # If this was the final trial in a block, start a break
    elif trial_number == trials_per_block and block_number != blocks:
        text.setText('You have completed section %i of %i!\nWhen you are ready to continue, press SPACEBAR to begin the next section.' % (block_number, blocks))
        text.draw()
        win.flip()
        event.waitKeys(keyList=['space'], clearEvents=True)
        block_number += 1
        trial_number = 0
    
    # Move to next trial number
    trial_number += 1

###
# POST-EXPERIMENT
###

# After completing all trials, display the ending message
text.setText('You have completed section %i of %i!\nThank you for participating! Please let the researcher know you have finished.' % (block_number, blocks))
text.draw()
win.flip()

# Data should save automatically, but manually save a backup copy just in case
exp.saveAsWideText('data/%s_%s_bkp.csv' % (experiment_name, info_dict['subject']))

# Press any key to close the serial communication and window, then exit
event.waitKeys(clearEvents=True)
arduino_ser.close()
win.close()
core.quit()
