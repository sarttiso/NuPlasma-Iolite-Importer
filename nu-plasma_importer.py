#/ Type: Importer
#/ Name: NuPlasma Importer
#/ Authors: Adrian Tasistro-Hart
#/ Description: An importer for loading Nu Plasma .run files from a Plasma.
#/ References: None
#/ Version: 0.2.2
#/ Contact: adrian at tasistro-hart.com

import time
import numpy as np
import pandas as pd
import re
import datetime as datetime
import json
import os
import ntpath
import re
import pytz

m_fileName = ""

def setFileName(fileName):
    m_fileName = fileName

def accepted_files():
    return ".run"

def correct_format():
    """
    This method will be called by iolite when the user selects a file
    to import. Typically, it uses the provided name (stored in
    plugin.fileName) and parses as much of it as necessary to determine
    if this importer is appropriate to import the data. For example,
    although X Series II and Agilent data are both comma separated
    value files, they can be distinguished by the characteristic
    formatting in each. In our implementation, distinguishing the
    two is done with 'regular expressions' (QRegularExpression)
    parsing of the first several lines of the file.

    Keep in mind that there is nothing stopping you from just
    returning True (thus supporting all files!) or simply checking
    the file extension, but such generic checks can yield unexpected
    results. You cannot be sure which order the various importer
    plugins will be checked for compatibility.

    This method must return either True or False.
    """
    _, ext = os.path.splitext(importer.fileName)

    if ext == '.run':
        return True
    else: 
        return False

def import_data():
    """
    see intro.py for explanation of functions
    """

    IoLog.debug(f'Importer path: {os.path.split(importer.pythonPath)[0]}')
    # load the data file and determine the nrf code to look for
    nrf_path = pd.read_table(importer.fileName, 
                            skiprows=65,
                            nrows=1,
                            header=None).iloc[0, 0]
    nrf_name = ntpath.basename(nrf_path)
    
    masses, elements, datacols = match_nrf(nrf_name)
    
    # read .run file
    run = pd.read_table(importer.fileName, 
                        skiprows=69, 
                        delimiter=',',
                        header=None,
                        names=datacols+['analysis number', '0'])
    
    
    # time increment between measurements
    dt = float(pd.read_table(importer.fileName, skiprows=4, nrows=1, delimiter=',', header=None).iloc[0,0])

    start_time = pd.read_table(importer.fileName, 
                               nrows=1, 
                               skiprows=67, 
                               header=None, 
                               delimiter=',')
    start_time = pd.to_datetime(start_time.iloc[0,0] + ' ' + start_time.iloc[0, 1], format='%d/%m/%Y %I:%M %p')

    # specify the time zone
    tz = pytz.timezone('US/Pacific')

    # update start time to reflect time zone
    start_time = tz.localize(start_time)

    time_vec = np.asarray([start_time+datetime.timedelta(seconds=dt*i) for i in range(len(run))])

    end_time = time_vec[-1]

    # make time vector in unix epoch seconds
    time_vec_unix_epoch = np.array([x.timestamp() for x in time_vec])

    IoLog.debug("Start time is: " + start_time.strftime('%Y-%m-%d %H:%M:%S'))
    
    # set time vector as index for dataframe (not actually necessary but oh well)
    run.set_index(time_vec, inplace=True)

    # add channels to iolite
    for ii, mass in enumerate(masses):
        channel = data.createTimeSeries(
            datacols[ii], data.Input, time_vec_unix_epoch, run[datacols[ii]].values
        )
        channel.setProperty("Mass", mass)
        channel.setProperty("Units", "volts")
        channel.setProperty("Machine Name", 'Nu Plasma')

    # Now calculate Total Beam:
    data.calculateTotalBeam()

    IoLog.debug("Import Time: " + datetime.datetime.now().strftime("%d,%m,%Y,%I,%M,%S,%p"))
    IoLog.debug("No Of Points: {}".format(len(run.index)))
    # IoLog.debug("Mass list: " + ', '.join(masses))
    
    # add some metadata
    data.createFileSampleMetadata('sample_name', start_time, end_time, importer.fileName)
    data.createImportedFileMetadata(start_time, end_time, importer.fileName, datetime.datetime.now(), len(run.index), datacols)

    importer.message('Finished')
    importer.progress(100)
    importer.finished()

    
def match_nrf(nrf_name):
    """Given the name of an nrf file, this function searches for it in the json file and
    returns the detector and mass combinations for the nrf file.

    Plasma .run files don't include any column header names to identify
    detectors/masses, so the column ordering is used to match masses.

    Args:
        nrf_name (str): string ending in .nrf corresponding to one of the entries in the
                        json file
    """
    # load nrf codes
    nrf_codes_path = os.path.join(os.path.split(importer.pythonPath)[0], 'nrf_codes_plasma.json')
    with open(nrf_codes_path) as json_file:
        nrfs = json.load(json_file)['nrfs']

    # find match
    nrf_names = np.array([x['name'] for x in nrfs])
    idx = nrf_names == nrf_name

    assert np.sum(idx) > 0, 'No matches for the given nrf file'
    assert np.sum(idx) <= 1, 'More than one match for the given nrf file'

    # having found a match, prepare arrays for masses, elements, and data columns
    nrf = nrfs[np.argwhere(idx).squeeze()]
    masses  = [re.search(r'\d+(\.\d+)?', x).group(0)
              for x in nrf['masses']]
    elements = [re.findall('[a-zA-Z]+', x)[0] for x in nrf['masses']]
    datacols = [str(masses[ii])+elements[ii] for ii in range(len(masses))]

    return masses, elements, datacols