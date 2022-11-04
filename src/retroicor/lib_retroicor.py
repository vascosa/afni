__authors__ = "Joshua Zosky and Peter Lauren"

"""
    2022 Peter Lauren
    peterdlauren@gmail.com

    This file contains all the library functions for "RetroTS2".
    "RetroTS2" is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    "RetroTS2" is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    You should have received a copy of the GNU General Public License
    along with "RetroTS".  If not, see <http://www.gnu.org/licenses/>.
    
        TODO:
        - Align names of variables
"""

import numpy as np
import matplotlib as mpl
from matplotlib import figure as mplf
import matplotlib.pyplot as plt
import math
import scipy
from scipy import signal as sps
import pandas as pd
import gzip
import json
import statistics

# Local libraries
import libPeakFilters as lpf


# Global constants
GLOBAL_M = 3
numSections = 1
NUM_RVT = 5

# Global variables
OutDir = "."

# for checking whether quotients are sufficiently close to integral
g_epsilon = 0.00001

    
def setOutputDirectory(directory):
    """
    NAME
        setOutputDirectory
            Set directory to which all files are written
        
    TYPE
        void
        
    SYNOPSIS
        setOutputDirectory(directory)
        
    ARGUMENTS
        directory:   string variable specifying the output directory
    AUTHOR
       Peter Lauren
    """
    global OutDir
    OutDir = directory

def readArray(parameters, key):
    """
    NAME
        readArray
            Read an array from an input file specified by the key in the parameters field
            
    TYPE
        <class 'list'>
        
    SYNOPSIS
        readArray(parameters, key)
        
    ARGUMENTS
        parameters:   dictionary of input parameters which includes a 'key' field.
        
        key       :   (dType = str) key to file of interest
   AUTHOR
       Peter Lauren
    """

    # Read single column of numbers into list of lists
    with open(parameters[key]) as f:
        array = []
        for line in f: # read rest of lines
            array.append([float(x) for x in line.split()])
            
    # Transform list of lists into single list
    array = [n for one_dim in array for n in one_dim]
    return array

def getCardiacPeaks(parameters, rawData, filterPercentile=70.0):
   """
   NAME
       getCardiacPeaks
           Get peaks from cardiac time series supplied as an ASCII 
           file with one time series entry per line
           
    TYPE
        <class 'numpy.ndarray'>, int
   SYNOPSIS
       getCardiacPeaks(parameters)
   ARGUMENTS
       parameters:   dictionary of input parameters which includes the following fields.
       
           phys_fs: (dType = float) Sampling frequency in Hz
           
           verbose: (dtype = bool) Whether running in verbose mode.  (Save graphs, 
                    of intermediate steps, to disk.)
           
           dev:     (dType = bool) Whether running in development mode.  (Show 
                                            graphs and pause between graphs.)
       
       rawData: (dType = float, array) Raw cardiac data
       
       filterPercentile: (dType = float) Minimum percentile of raw data for a 
                           peak value to imply a valid peak
   AUTHOR
       Peter Lauren
   """
   
   #DEBUG
   oldArray = rawData
   # # Debug
   # array = oldArray[0:200000]
   
   # Check for nan's
   failureThreshold = parameters['phys_fs'] / 4 # Consecutive NaNs cannot cover more than about 0.25 s
   rawData = lpf.checkForNans(rawData, "cardiac", failureThreshold = failureThreshold)
   if len(rawData) == 0:
       print('*** ERROR: Could not handle all of the NaN values')
   
   MIN_HEART_RATE = 25  # Minimum HR in BPM
    
   # Determine lower bound based based on minimum HR
   minBeatsPerSecond = MIN_HEART_RATE/60
   
   # Remove NaNs from raw data
   rawData = [x for x in rawData if math.isnan(x) == False]
    
   global OutDir
   
   # Band pass filter raw data
   filterData = lpf.bandPassFilterRawDataAroundDominantFrequency(rawData, minBeatsPerSecond,\
        parameters["phys_fs"], graph = True, saveGraph = parameters["verbose"],\
        OutDir=OutDir)
   if len(filterData) == 0:
       print('Failed to band-pass filter cardiac data')   
       return []
   
   # Get initial peaks using window that is an tenth of a second  (HR <+ 680 BPM)
   peaks, _ = sps.find_peaks(np.array(filterData), width=int(parameters["phys_fs"]/40))
   
   # Graph initial peaks and save graph to disk
   if parameters['verbose']:
       lpf.graphPeaksAgainstRawInput(rawData, peaks, parameters["phys_fs"], "Cardiac", 
            OutDir = OutDir, prefix = 'cardiacPeaksFromBPFInput', 
            caption = 'Cardiac peaks from band-pass filtered input.')
   
   # Adjust peaks from uniform spacing
   peaks = lpf.refinePeakLocations(peaks, rawData, graph = parameters['verbose'],
             dataType = "Cardiac",  phys_fs = parameters["phys_fs"], 
            saveGraph = parameters['verbose'], OutDir = OutDir)
    
   # Remove peaks that are less than the required percentile of the local input signal
   peaks = lpf.localPercentileFilter(peaks, rawData, filterPercentile, numPeriods=3, 
            graph = parameters['verbose'], dataType = "Cardiac",  
            phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
   if len(peaks) == 0:
        print('*** ERROR: Failure to local percentile filter cardiac peaks')
        return [], 0

   # Estimate the overall typical period using filtered cardiac time series
   period = lpf.getTimeSeriesPeriod(filterData) 
   if period < 0:     
        print('*** ERROR: Failure to get typical period using filtered cardiac time series')
        return [], 0
    
   # Merge peaks that are closer than one quarter of the overall typical period
   peaks = lpf.removeClosePeaks(peaks, period, rawData, 
        graph = parameters['verbose'], dataType = "Cardiac",  
        phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
   
   # Remove "peaks" that are less than the raw input a quarter of a period on right side
   # This is tomove false peaks on the upstroke
   # searchLength = round(parameters["-phys_fs"]/16)
   peaks = lpf.removePeaksCloseToHigherPointInRawData(peaks, rawData, period=period, 
        graph = parameters['verbose'], dataType = "Cardiac",  
        phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
   if len(peaks) == 0:
       print('ERROR in getCardiacPeaks: Peaks array empty')
       return peaks, len(rawData)
    
   # Remove false peaks on the downstroke
   peaks = lpf.removePeaksCloseToHigherPointInRawData(peaks, rawData, direction='left', period=period, 
        graph = parameters['verbose'], dataType = "Cardiac",  
        phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
    
   # Remove peaks that are less than a quarter as far from the local minimum to the adjacent peaks
   peaks = lpf.removePeaksCloserToLocalMinsThanToAdjacentPeaks(peaks, rawData, 
        graph = parameters['verbose'], dataType = "Cardiac",  
        phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)

   # Add missing peaks
   peaks = lpf.addMissingPeaks(peaks, rawData, period=period)   
   
           
     # Check for, and fill in, missing peaks - MAKE OWN FUNCTION
   # interpeak = [x - peaks[i - 1] for i, x in enumerate(peaks)][1:]
   # minSep = min(interpeak)
   # Threshold = minSep * 2
   # numPeaks = len(peaks)
   # for p in range(numPeaks-2,-1,-1):
   #      if interpeak[p] > Threshold:
   #          numberToAdd = int(round(interpeak[p]/minSep))
   #          sep = round(interpeak[p]/numberToAdd)
   #          if sep < minSep:
   #              numberToAdd = numberToAdd - 1
   #              sep = round(interpeak[p]/numberToAdd)               
   #          for i in range(1,numberToAdd):
   #              peaks = np.insert(peaks, p+i, peaks[p]+i*sep)
    
   # Graph respiratory peaks and troughs against respiratory time series
   if parameters['dev']:
       lpf.graphPeaksAgainstRawInput(rawData, peaks, parameters["phys_fs"], "Cardiac",
            OutDir = OutDir, prefix = 'cardiacPeaksFinal', 
            caption = 'Cardiac peaks after all filtering.')
               
   # # Graph cardiac peaks against cardiac time series
   # x = []    
   # end = len(rawData)
   # for i in range(0,end): x.append(i/parameters["phys_fs"])
   # peakVals = []
   # for i in peaks: peakVals.append(rawData[i])
   # mplf.Figure(figsize =(7,7))
   # mpl.pyplot.subplot(211)
   # mpl.pyplot.plot(x, rawData, "g") #Lines connecting peaks and troughs
   # mpl.pyplot.plot(peaks/parameters["phys_fs"], peakVals, "ro") # Peaks
   # mpl.pyplot.xlabel("time(s)")
   # mpl.pyplot.ylabel("Input data input value")
   # mpl.pyplot.title("Cardiac peaks (red) and raw input data (green)",\
   #             fontdict={'fontsize': 12})
        
   # # Save plot to file
   # mpl.pyplot.savefig('%s/cardiacPeaks.pdf' % (OutDir)) 
   # mpl.pyplot.show()  # If this is left out, output file is blank
    
   return peaks, len(rawData)


def getRespiratoryPeaks(parameters, rawData):
    """
    NAME
    getRespiratoryPeaks
    Get peaks from repiratory time series supplied as an ASCII 
    file with one time series entry per line
    TYPE
    <class 'numpy.ndarray'>, int
    SYNOPSIS
    respFile(parameters)
    ARGUMENTS
        parameters:   dictionary of input parameters which includes the following fields.
    
        rawData: (dType = float, array) Raw cardiac data
    AUTHOR
    Peter Lauren
    """

    # DEBUG
    oldArray = rawData
    
    global OutDir
   
    # Check for nan's
    rawData = lpf.checkForNans(rawData, "Respiratory")
   
    # Set maximum breathing period of 10 seconds
    MAX_BREATHING_PERIOD_IN_SECONDS = 10
    
    # Determine lower bound based based on minimum HR
    minBreathsPerSecond = 1.0/MAX_BREATHING_PERIOD_IN_SECONDS
   
    # Band pass filter raw data
    filterData = lpf.bandPassFilterRawDataAroundDominantFrequency(rawData, minBreathsPerSecond,\
        parameters["phys_fs"], graph = True, saveGraph = parameters["verbose"],\
        OutDir=OutDir)
    if len(filterData) == 0:
       print('Failed to band-pass filter cardiac data')   
       return []
   
    # Get initial peaks using window that is an eighth of a second  (BR <+ 480 BPM)
    # peaks, _ = sps.find_peaks(np.array(rawData), width=int(parameters["phys_fs"]/4))
    peaks, _ = sps.find_peaks(np.array(filterData), width=int(parameters["phys_fs"]/4))
   
    # Graph initial peaks and save graph to disk
    if parameters['verbose']:
       lpf.graphPeaksAgainstRawInput(rawData, peaks, parameters["phys_fs"], "Respiratory", 
            OutDir = OutDir, prefix = 'respiratoryPeaksFromBPFInput', 
            caption = 'Respiratory peaks from band-pass filtered input.')
   
    # Adjust peaks from uniform spacing
    peaks = lpf.refinePeakLocations(peaks, rawData, graph = parameters['verbose'],
             dataType = "Respiratory",  phys_fs = parameters["phys_fs"], 
            saveGraph = parameters['verbose'], OutDir = OutDir)
    
    # Get period from filtered input data 
    period = lpf.getTimeSeriesPeriod(filterData)
    if period < 0:     
        print('*** ERROR: Failure to get typical period using filtered respiratory time series')
        return [], [], 0
    
    # Remove peaks that are less than the 10th percentile of the input signal
    peaks = lpf.percentileFilter(peaks, rawData, percentile=10.0, 
             graph = parameters['verbose'], dataType = "Respiratory",  
             phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
    if len(peaks) == 0:
        print('*** ERROR: Failure to percentile filter respiratory peaks')
        return [], [], 0
    
    # Remove "peaks" that are less than the raw input a quarter of a period on right side
    # This is tomove false peaks on the upstroke
    peaks = lpf.removePeaksCloseToHigherPointInRawData(peaks, rawData, period=period, 
             graph = parameters['verbose'], dataType = "Respiratory",  
             phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
    
    # Remove false peaks on the downstroke
    peaks = lpf.removePeaksCloseToHigherPointInRawData(peaks, rawData, direction='left', period=period, 
             graph = parameters['verbose'], dataType = "Respiratory",  
             phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
    
    # Remove peaks that are less than a quarter as far from the local minimum to the adjacent peaks
    peaks = lpf.removePeaksCloserToLocalMinsThanToAdjacentPeaks(peaks, rawData, 
             graph = parameters['verbose'], dataType = "Respiratory",  
             phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
    
    # Merge peaks that are closer than one quarter of the overall typical period
    peaks = lpf.removeClosePeaks(peaks, period, rawData, 
             graph = parameters['verbose'], dataType = "Respiratory",  
             phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)

    # Add missing peaks
    peaks = lpf.addMissingPeaks(peaks, rawData, period=period, 
             graph = parameters['verbose'], dataType = "Respiratory",  
             phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)   
    
    # Remove "peaks" that are less than the raw input a quarter of a period on right side
    # This is tomove false peaks on the upstroke
    peaks = lpf.removePeaksCloseToHigherPointInRawData(peaks, rawData, period=period, 
             graph = parameters['verbose'], dataType = "Respiratory",  
             phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
    
    # Remove false peaks on the downstroke
    peaks = lpf.removePeaksCloseToHigherPointInRawData(peaks, rawData, direction='left', period=period, 
             graph = parameters['verbose'], dataType = "Respiratory",  
             phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
    
    # troughs, _ = sps.find_peaks(-np.array(rawData), width=int(parameters["phys_fs"]/8))
    troughs, _ = sps.find_peaks(-np.array(filterData), width=int(parameters["phys_fs"]/8))
   
    # Graph initial peaks and save graph to disk
    if parameters['verbose']:
       lpf.graphPeaksAgainstRawInput(rawData, peaks, parameters["phys_fs"], "Respiratory", 
            troughs = troughs, OutDir = OutDir, prefix = 'respiratoryPeaksFromBPFInput', 
            caption = 'Respiratory troughs from band-pass filtered input.')
    
    # Remove troughs that are more than the 90th percentile of the input signal
    troughs = lpf.percentileFilter(troughs, rawData, percentile=90.0, upperThreshold=True, 
             graph = parameters['verbose'], dataType = "Respiratory",  
             phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
    if len(troughs) == 0:
        print('*** ERROR: Failure to percentile filter respiratory troughs')
        return [], [], 0
    
    # Remove "troughs" that are greater than the raw input a quarter of a period on right side
    # This is to remove false troughs on the downstroke
    troughs = lpf.removeTroughsCloseToLowerPointInRawData(troughs, rawData, period=period, 
             graph = parameters['verbose'], dataType = "Respiratory",  
             phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
    
    # Remove false troughs on the uptroke
    troughs = lpf.removeTroughsCloseToLowerPointInRawData(troughs, rawData,\
            period=period, direction = 'left', 
            graph = parameters['verbose'], dataType = "Respiratory",  
            phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
    
    # Remove troughs that are less than a quarter as far from the local maximum to the adjacent troughs
    troughs = lpf.removeTroughsCloserToLocalMaxsThanToAdjacentTroughs(troughs, rawData, 
        graph = parameters['verbose'], dataType = "Respiratory",  
        phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
    
    # Merge troughs that are closer than one quarter of the overall typical period
    troughs = lpf.removeClosePeaks(troughs, period, rawData, Troughs = True, 
        graph = parameters['verbose'], dataType = "Respiratory",  
        phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
    
    # Remove peaks/troughs that are also troughs/peaks
    peaks, troughs = lpf.removeOverlappingPeaksAndTroughs(peaks, troughs, rawData, 
        graph = parameters['verbose'], dataType = "Respiratory",  
        phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
    
    # Remove extra peaks bewteen troughs and troughs between peaks
    # peaks, troughs = lpf.removeExtraInterveningPeaksAndTroughs(peaks, troughs, rawData)
    
    # Add missing peaks and troughs
    peaks, troughs = lpf.addMissingPeaksAndTroughs(peaks, troughs, rawData, period=None, 
        graph = parameters['verbose'], dataType = "Respiratory",  
        phys_fs = parameters["phys_fs"], saveGraph = parameters['verbose'], OutDir = OutDir)
    
    # Remove extra peaks bewteen troughs and troughs between peaks
    # peaks, troughs = lpf.removeExtraInterveningPeaksAndTroughs(peaks, troughs, rawData)
    
    # Filter peaks and troughs.  Reject peak/trough pairs where
    #    difference is less than one tenth of the total range
    # nPeaks = len(peaks)
    # nTroughs = len(troughs)
    # minNum = min(nPeaks,nTroughs)
    # ptPairs = [rawData[peaks[x]]-rawData[troughs[x]] for x in range(0,minNum)]
    # threshold = (max(rawData)-min(rawData))/10
    # indices2remove = list(filter(lambda x: ptPairs[x] <threshold, range(len(ptPairs))))
    # peaks = np.delete(peaks,indices2remove)
    # troughs = np.delete(troughs,indices2remove)
    
    # Graph respiratory peaks and troughs against respiratory time series
    if parameters['dev']:
        lpf.graphPeaksAgainstRawInput(rawData, peaks, parameters["phys_fs"], "Respiratory",\
                    troughs = troughs, caption = 'Respiratory peaks after all filtering.')
     
    return peaks, troughs, len(rawData)

def determineCardiacPhases(peaks, fullLength, phys_fs, rawData):
    """
    NAME
       determineCardiacPhases
           Determine phases, in the cardiac cycle based on the Glover (2000) paper
    TYPE
        <class 'list'>
    SYNOPSIS
       determineCardiacPhases(peaks, fullLength)
    ARGUMENTS
        peaks:   (dType int64 array) Peaks in input cardiac time series.  Type = <class 'numpy.ndarray'>.
        
        fullLength:   (dType = int) Lenagth of cardiac time series
        
        phys_fs:   (dType = float) Physiological signal sampling frequency in Hz. 
        
        rawData: (dType = float, array) Raw cardiac data
    AUTHOR
       Peter Lauren
    """

    phases = []
    inc = 0
    k = math.pi * 2
    numIntervals = len(peaks) - 1
    
    # Assign -1 to phases of all time tpoints before the first peak
    for i in range(0,peaks[0]): phases.append(-1.0)
    
    # Get phases between peaks
    for i in range(0,numIntervals):
        start = peaks[i]
        end = peaks[i+1]
        period = end - start
        for j in range(start,end):
            phases.append((k*(j-start))/period)
            inc = inc+1
            
    # Estimate phases before first peak as the last 
    #   phases of the first full cycle
    iIndex =  peaks[1] -  peaks[0]
    for oIndex in range(0, peaks[0]):
      phases[oIndex] =  phases[iIndex] 
      iIndex = iIndex + 1
            
    # Estimate phases before last peak as the first 
    #   phases of the last full cycle
    iIndex =  peaks[-2] + 1
    tailLength = fullLength - peaks[-1]
    for i in range(0,tailLength):
      phases.append(phases[iIndex]) 
      iIndex = iIndex + 1
      
    # Move phase range from [0,2Pi] to [-Pi,Pi]
    phases = [x - math.pi for x in phases]
      
    # PLot phases
    x = []    
    end = min(len(phases),round(len(phases)*50.0/len(peaks)))
    for i in range(0,end): x.append(i/phys_fs)
    fig, ax_left = mpl.pyplot.subplots()
    mpl.pyplot.xlabel("Time (s)")
    mpl.pyplot.ylabel('Input data input value',color='g')
    ax_right = ax_left.twinx()
    ax_right.plot(x, phases[0:end], color='red')
    ax_left.plot(x, rawData[0:end], color='green')
    mpl.pyplot.ylabel('Phase (Radians)',color='r')
    mpl.pyplot.title("Cardiac phase (red) and raw input data (green)")
        
    # Save plot to file
    mpl.pyplot.savefig('%s/CardiacPhaseVRawInput.pdf' % (OutDir)) 
    mpl.pyplot.show()
            
    return phases

def getACoeffs(parameters, key, phases):
    """
    NAME
       getACoeffs
           Determine a coefficients from equation 4 of Glover (2000) paper (equation 4)
    TYPE
        <class 'list'>
    SYNOPSIS
       getACoeffs(parameters, key, phases)
    ARGUMENTS
        parameters:   dictionary of input parameters which includes a 'key' field.
        
        key       :   key to file of interest
        
        phases    :   <class 'list'> containing phases determined as described in Glover (2000) paper
    AUTHOR
       Peter Lauren
    """

    data = readArray(parameters, key)
    mean = np.mean(data)
    N = len(data)
    global GLOBAL_M
    a = []
    for m in range(1,GLOBAL_M):
        num = 0
        denom = 0
        for n in range(0,N):
            num = num + (data[n]-mean)*math.cos(m*phases[n])
            temp = math.cos(m*phases[n])
            denom = denom + (temp*temp)
        a.append(num/denom)
        
    return a

def getBCoeffs(parameters, key, phases):
    """
    NAME
       getBCoeffs
           Determine b coefficients from equation 4 of Glover (2000) paper (equation 4)
    TYPE
        <class 'list'>
    SYNOPSIS
       getBCoeffs(parameters, key, phases)
    ARGUMENTS
        parameters:   dictionary of input parameters which includes a 'key' field.
        
        key       :   key to file of interest
        
        phases    :   <class 'list'> containing phases determined as described in Glover (2000) paper
    AUTHOR
       Peter Lauren
    """

    data = readArray(parameters, key)
    mean = np.mean(data)
    N = len(data)
    global M
    b = []
    for m in range(1,M):
        num = 0
        denom = 0
        for n in range(0,N):
            num = num + (data[n]-mean)*math.sin(m*phases[n])
            temp = math.sin(m*phases[n])
            denom = denom + (temp*temp)
        b.append(num/denom)
        
    return b
            

def determineRespiratoryPhases(parameters, respiratory_peaks, respiratory_troughs, phys_fs, rawData):
    """
    NAME
        determineRespiratoryPhases
            Determine respiratory phases as descibed in Glover (2000) paper (equation 3)
    TYPE
        <class 'list'>
    SYNOPSIS
       determineRespiratoryPhases(parameters, respiratory_peaks, respiratory_troughs)
    ARGUMENTS
        parameters:   dictionary of input parameters which includes the following fields.
            -respFile;   Name of ASCII file with respiratory time series
            phys_fs:     Physiological signal sampling frequency in Hz.
        
        respiratory_peaks      :   peaks in respiratory time series.  Type = <class 'numpy.ndarray'>
        
        respiratory_troughs    :   <class 'numpy.ndarray'> containing troughs in the respiratory time series
        
        phys_fs:     Physiological signal sampling frequency in Hz 
        
        rawData:     Raw respiratory data
        
    AUTHOR
       Peter Lauren
    """
    
    # DEBUG
    # rawData = rawData[3000:4000]
    # respiratory_peaks = np.array([n for n in respiratory_peaks if n > 3000 and n<4000]) - 3000
    # respiratory_troughs = np.array([n for n in respiratory_troughs if n > 3000 and n<4000]) - 3000
    # respiratory_peaks - 3000
    # respiratory_troughs - 3000
    
    rawData = rawData - min(rawData)
    
    NUM_BINS = 100
    
    # Determine whether currently inspiration or expiration
    if respiratory_peaks[0] < respiratory_troughs[0]:
        polarity = 1
    else:
        polarity = -1
        
    # Number of segments where each segment is either inspiration or expiration
    numFullSegments = len(respiratory_peaks) + len(respiratory_troughs) - 1
    
    # Initialize array of output phases
    phases = np.zeros(len(rawData))
    
    # Assign values to time series before first full segment
    peakIndex = 0
    troughIndex = np.argmin(respiratory_troughs)
    start = 0
    finish = min(respiratory_peaks[peakIndex], respiratory_troughs[troughIndex])
    if finish == 0:
        finish = max(respiratory_peaks[peakIndex], respiratory_troughs[troughIndex])
    denom = finish  # Total length of segment
    
    # Histogram values in segment
    sample = [x - rawData[respiratory_troughs[troughIndex]] for x in rawData[start:finish]] 
    # sample = sample - min(sample)
    counts, bins = np.histogram(sample, bins=NUM_BINS) 
    
    # Determine phase based on equation 3 is Glover paper
    if polarity > 0: Rmax = max(sample)
    else: Rmax = rawData[respiratory_peaks[0]] # Maximum value in segment
    for i in range(start,finish): # Move through segment
        end = round(sample[i]*NUM_BINS/Rmax) # Summation limit
        
        # Count values, in segment that are not greater than the summation limit
        count = 0
        end = min(end,len(counts)-1)
        for j in range(0,end):
            count = count + counts[j]
            
        # Use result to estimate phase at given time point
        phases[i] = (math.pi*count*polarity)/denom
    
    # Switch polarity and increment peak indxe if new polarity inspiration
    #   Otherwise increment trough index instead
    polarity = -polarity
    if polarity > 0: peakIndex = peakIndex + 1
    else: troughIndex = troughIndex + 1
    
    peakIndex = 0
    troughIndex = 0
    for segment in range(0,numFullSegments):    # Process each segment in turn
    
        # Determine segment from the peak and trough indices
        start = min(respiratory_peaks[peakIndex], respiratory_troughs[troughIndex])
        finish = max(respiratory_peaks[peakIndex], respiratory_troughs[troughIndex])
        denom = finish - start  # Total length of segment
        
        # Histogram values in segment
        sample = [x - rawData[respiratory_troughs[troughIndex]] for x in rawData[start:finish]] 
        sample = sample - min(sample)
        counts, bins = np.histogram([x for x in sample if math.isnan(x) == False], bins=NUM_BINS) 
        
        # Determine phase based on equation 3 is Glover paper
        Rmax = max(sample) # Maximum value in segment
        for i in range(start,finish): # Move through segment
            end = round(sample[i-start]*NUM_BINS/Rmax) # Summation limit
            
            # Count values, in segment that are not greater than the summation limit
            count = 0
            end = min(end, len(counts))
            if end > 0:
                for j in range(0,end):
                    count = count + counts[j]
                
            # Use result to estimate phase at given time point
            phases[i] = (math.pi*count*polarity)/denom
            
        # Switch polarity and increment peak indxe if new polarity inspiration
        #   Otherwise increment trough index instead
        polarity = -polarity
        if polarity > 0: peakIndex = peakIndex + 1
        else: troughIndex = troughIndex + 1
        if peakIndex>=len(respiratory_peaks) or troughIndex>=len(respiratory_troughs): break
    
    # Assign values to time series after last full segment
    start = finish
    finish = len(rawData)
    denom = finish - start  # Total length of segment
    
    # Histogram values in segment
    sample = [x - rawData[respiratory_troughs[-1]] for x in rawData[start:finish]]  
    counts, bins = np.histogram(sample, bins=NUM_BINS) 
    
    # Determine phase based on equation 3 is Glover paper
    if polarity < 0: Rmax = max(sample)
    else: Rmax = rawData[respiratory_peaks[-1]] # Maximum value in segment
    for i in range(start,finish): # Move through segment
        end = round(sample[i-start]*NUM_BINS/Rmax) # Summation limit
        
        if end >= len(counts):
            end = len(counts) - 1
        
        # Count values, in segment that are not greater than the summation limit
        count = 0
        for j in range(0,end):
            count = count + counts[j]
            
        # Use result to estimate phase at given time point
        phases[i] = (math.pi*count*polarity)/denom
    
      
    # PLot phases and raw data against time in seconds.
    peakVals = []
    for i in respiratory_peaks: peakVals.append(rawData[i])
    troughVals = []
    for i in respiratory_troughs: troughVals.append(rawData[i])
    x = []    
    end = min(len(phases),round(len(phases)*50.0/len(respiratory_peaks)))
    for i in range(0,end): x.append(i/phys_fs)
    fig, ax_left = mpl.pyplot.subplots()
    mpl.pyplot.xlabel("Time (s)")
    mpl.pyplot.ylabel('Input data input value',color='g')
    ax_right = ax_left.twinx()
    # ax_right.plot(x[3000:4000], phases[3000:4000], color='red')
    # ax_left.plot(x[3000:4000], rawData[3000:4000], color='green')
    ax_right.plot(x, phases[0:end], color='red')
    ax_left.plot(x, rawData[0:end], color='green')
    # ax_left.plot(respiratory_peaks/parameters["phys_fs"], peakVals, "mo") # Peaks
    # ax_left.plot(respiratory_troughs/parameters["phys_fs"], troughVals, "bo") # troughs
    mpl.pyplot.ylabel('Phase (Radians)',color='r')
    mpl.pyplot.title("Respiratory phase (red) and raw input data (green)")
        
    # Save plot to file
    mpl.pyplot.savefig('%s/RespiratoryPhaseVRawInput.pdf' % (OutDir)) 
    mpl.pyplot.show()
    
        
    return phases

def getPhysiologicalNoiseComponents(parameters):
    """
    NAME
        getPhysiologicalNoiseComponents 
            Return physiological (respiratory and cardiac) contamination components of BOLD signal
    TYPE
        <class 'pandas.core.frame.DataFrame'>
    SYNOPSIS
       getPhysiologicalNoiseComponents(parameters)
    ARGUMENTS
        parameters:   Dictionary with the following fields.
        
            -respFile:   file containing respiratory time series
            
            -cardFile:   file containing cardiac time series
            
            -aby     :   whether  a and b coefficients as per Glover et al, Magnetic 
                                        Resonance in Medicine 44:162–167 (2000)
                                        
            -niml    :   whether output should be in niml format instead of CSV
            
    AUTHOR
       Peter Lauren
    """
    
    # Initializations
    respiratory_phases = np.array([]) #None
    cardiac_phases     = []           #
    
    # Parameters to read in raw data
    rawDataParams = dict()
    if 'StartTime' in parameters: rawDataParams['StartTime'] = parameters['StartTime']
    rawDataParams["phys_fs"] = parameters["phys_fs"]
    
    # Process cardiac data if any
    if parameters["-cardFile"] or len(parameters["phys_cardiac_dat"]) > 0:           
        # rawData = readArray(parameters, '-cardFile')
        rawData = readRawInputData(rawDataParams, parameters["-cardFile"], parameters["phys_cardiac_dat"])
        if len(rawData) == 0:
            print('Error reading input cardiac data')
            return []
        
        # if not parameters['phys_fs']: # Sampling frequency not supplied
        #     parameters['phys_fs'] = lpf.estimateSamplingFrequencyFromRawData(rawData, 70)
                
        cardiac_peaks, fullLength = getCardiacPeaks(parameters, rawData) 
        if len(cardiac_peaks) == 0:
            print('ERROR in getPhysiologicalNoiseComponents: No cardiac peaks')
            return []
        
        if len(cardiac_peaks) > 0:
            cardiac_phases = determineCardiacPhases(cardiac_peaks, fullLength,\
                                                parameters['phys_fs'], rawData)
        
    # Process respiratory data if any
    if parameters["-respFile"] or len(parameters["phys_resp_dat"]) > 0:

        # rawData = readArray(parameters, '-respFile')
        rawData = readRawInputData(rawDataParams, parameters["-respFile"], parameters["phys_resp_dat"])
        if len(rawData) == 0:
            print('Error reading input respiratory data')
            return []
        
        respiratory_peaks, respiratory_troughs, fullLength = \
            getRespiratoryPeaks(parameters, rawData) 
        if len(respiratory_peaks) == 0:
            print('*** EOORO: Error getting respiratory peaks or troughs')
            return []
            
        
        respiratory_phases = determineRespiratoryPhases(parameters, \
                respiratory_peaks, respiratory_troughs, parameters['phys_fs'], \
                    [x for x in rawData if math.isnan(x) == False])
        
    if (parameters['-aby']):    # Determine a and b coefficients as per Glover et al, Magnetic 
                                # Resonance in Medicine 44:162–167 (2000)
        # Get a coefficients
        cardiacACoeffs = getACoeffs(parameters, '-cardFile', cardiac_phases)
        respiratoryACoeffs = getACoeffs(parameters, '-respFile', respiratory_phases)
        
        # Get b coefficients
        cardiacBCoeffs = getBCoeffs(parameters, '-cardFile', cardiac_phases)
        respiratoryBCoeffs = getBCoeffs(parameters, '-respFile', respiratory_phases)
    else:   # a and b coefficients set to 1.0
        cardiacACoeffs = [1.0]
        respiratoryACoeffs = [1.0]
        cardiacBCoeffs = [1.0]
        respiratoryBCoeffs = [1.0]
        cardiacACoeffs.append(1.0)
        respiratoryACoeffs.append(1.0)
        cardiacBCoeffs.append(1.0)
        respiratoryBCoeffs.append(1.0)
    
    global GLOBAL_M
    
    # Initialize output table
    df = pd.DataFrame()
    
    # Make output table columns names
    columnNames = []
    numSections = parameters["-s"]
    len_resp = len(respiratory_phases)
    len_card = len(cardiac_phases)
    if len_resp:
        for s in range(0,numSections):
            for r in range(0,4):
                string = 's' + str(s) + '.Resp' + str(r)
                columnNames.append(string)
    if len_card:
        for s in range(0,numSections):
            for r in range(0,4):
                string = 's' + str(s) + '.Card' + str(r)
                columnNames.append(string)
        
    # Make output table data matrix
    data = []
    len_resp = len(respiratory_phases)
    len_card = len(cardiac_phases)

    if len_resp and len_card :
        T = min(len_resp, len_card)
    elif len_resp :
        T = len_resp
    elif len_card :
        T = len_card
    print('T = ', T)

    nreg = 0              # number of regressors we make
    for t in range(0,T):
        # sum = 0
        addend = []
        if len_resp :
            for m in range(1,GLOBAL_M):
                m0 = m - 1
                addend.append(respiratoryACoeffs[m0]*math.cos(m*respiratory_phases[t]))
                addend.append(respiratoryBCoeffs[m0]*math.sin(m*respiratory_phases[t]))
                if not(t):
                    nreg+= 2
        if len_card:
            for m in range(1,GLOBAL_M):
                m0 = m - 1
                addend.append(cardiacACoeffs[m0]*math.cos(m*cardiac_phases[t]))
                addend.append(cardiacBCoeffs[m0]*math.sin(m*cardiac_phases[t]))
                if not(t):
                    nreg+= 2
        data.append(addend)

    # Reshape matrix according to number of slices
    nrow = np.shape(data)[0]
    print("DEBUG: nrow =", nrow)
    print("DEBUG: shape BEFORE =", np.shape(data))
    print("DEBUG: nsections =", numSections)
    data = np.reshape(data[0:nrow-(nrow%numSections)][:], (nreg*numSections, -1)).T
    print("DEBUG: shape AFTER =", np.shape(data))
    
    df = pd.DataFrame(data,columns=columnNames)
        
    # return df   
    physiologicalNoiseComponents = dict()
    physiologicalNoiseComponents['respiratory_phases'] = respiratory_phases
    physiologicalNoiseComponents['cardiac_phases'] = cardiac_phases
    return physiologicalNoiseComponents

def readRawInputData(respcard_info, filename=None, phys_dat=None):
    """
    NAME
        readRawInputData 
            Read in raw input data according to the user=supplied program arguments.
            Outputs raw data.
    TYPE
        <class 'numpy.ndarray'> 
    SYNOPSIS
       readRawInputData(respcard_info, filename=None, phys_dat=None)
    ARGUMENTS
        respcard_info:   Dictionary with the following fields.
        
            StartTime:   (Optional)  Time at which the signal of interest starts
            
            phys_fs:   (dType = float) Physiological signal sampling frequency in Hz.
                   
        filename:   String giving the local name of the input file
        
        phys_dat:   BIDS style physio file
        
    AUTHOR
       Peter Lauren
    """

    if phys_dat is None or len(phys_dat) == 0: # No BIDS style physio file
        # Read repiration/cardiac file into phys_dat
        phys_dat = []
        with open(filename, "rb") as h:
            lineNumber = 0
            for entry in h:
                lineNumber = lineNumber + 1
                try:
                    float(entry)
                    if float(entry) != 5000.0: # Some files have artifactual entries of 5000.0
                        phys_dat.append(float(entry))
                except:
                    print('*** ERROR: invalid, non-numeric data entry: ', entry, 
                          ' at line ', lineNumber, ' of ', filename)
                    return []
            for line in h:
                phys_dat.append(float(line.strip()))
                
    v_np = np.asarray(phys_dat)
    
    # Trim leading datapoints if they precede start time
    if ('StartTime' in respcard_info and respcard_info['StartTime']<0):
        start_index = round(-respcard_info['StartTime'] * respcard_info["phys_fs"])
        print('start_index = ', start_index)
        v_np = v_np[start_index:-1]
    
    return v_np

def runAnalysis(parameters):
    """
    NAME
        runAnalysis 
            Run retroicor analysis as described by Glover (2000) and implemented by Peter Lauren
    TYPE
        void
    SYNOPSIS
       runAnalysis(parameters)
    ARGUMENTS
    
        parameters:   Dictionary with the following fields.
        
            -respFile:   file containing respiratory time series
            
            -cardFile:   file containing cardiac time series
            
            -aby: whether  a and b coefficients as per Glover et al, Magnetic  Resonance in Medicine 44:162–167 (2000)
                                        
            -niml: whether output should be in niml format instead of CSV
            
            -outputFileName:   Output filename
            
    AUTHOR
       Peter Lauren
    """
    
    physiologicalNoiseComponents = getPhysiologicalNoiseComponents(parameters)
    if len(physiologicalNoiseComponents) == 0:
        print('Error in runAnalysis. Failure to get physionlogical noise components')
        return 1
    if parameters['-niml']:
        return 0
    
    physiologicalNoiseComponents.to_csv(parameters['-outputFileName'])
    
    # PLot first 200 rows of dataframe
    colors = ['blue','cyan','blueviolet','cadetblue', 'olive','yellowgreen','red','magenta']
    physiologicalNoiseComponents.head(200).plot(color=colors)
    
    # Send output to terminal
    if (parameters['-abt']): print(repr(physiologicalNoiseComponents))
    

def getInputFileParameters(respiration_info, cardiac_info, phys_file,\
                        phys_json_arg, respiration_out, cardiac_out, rvt_out):
    """
    NAME
        getInputFileParameters 
            Returns the local respiriation file name  (if JSON file absent, None otherwise), 
            respiration file data (if JSON file present, None otherwise), the 
            local cardiac file name  (if JSON file absent, None otherwise), 
            cardiac file data (if JSON file present, None otherwise).
    TYPE
        <class 'str'>, <class 'numpy.ndarray'>, <class 'str'>, <class 'numpy.ndarray'>
    SYNOPSIS
       getInputFileParameters(respiration_info, cardiac_info, phys_file,
       phys_json_arg, respiration_out, cardiac_out, rvt_out)
    ARGUMENTS
        respiration_info:   Dictionary with the following fields.
        
            respiration_file:  (dType = str) Name of ASCII file with respiratory time series
            
            phys_fs:   (dType = float) Physiological signal sampling frequency in Hz.
            
        cardiac_info:   Dictionary with the following fields.
            
            phys_fs:   (dType = float) Physiological signal sampling frequency in Hz.
        
            cardiac_file:  (dType = str) Name of ASCII file with cardiac time series
            
        phys_file: (dType = NoneType) BIDS formatted physio file in tab separated format. May
                    be gzipped.
                
        phys_json_arg: (dType = NoneType) File metadata in JSON format
        
        respiration_out: (dType = int) Whether to have respiratory output
        
        cardiac_out:  (dType = int) Whether to have cardiac output
        
        rvt_out:  (dType = int) Whether to have RVT output
            
    AUTHOR
       Josh Zosky and Peter Lauren
    """
    
    # Initialize outputs
    respiration_file = None
    phys_resp_dat = []
    cardiac_file = None
    phys_cardiac_dat = []
            
    # Ensure there are no conflicting input file types
    # BIDS = Brain Imaging Data Structure
    if (((phys_file is not None) and (respiration_info["respiration_file"] is not None))
        or ((phys_file is not None) and (cardiac_info["cardiac_file"] is not None))):
        raise ValueError('You should not pass a BIDS style phsyio file'
                         ' and respiration or cardiac files.')
        
    # Get the peaks for respiration_info and cardiac_info
    # init dicts, may need -cardiac_out 0, for example   [16 Nov 2021 rickr]
    if phys_file:
        # Use json reader to read file data into phys_meta
        with open(phys_json_arg, 'rt') as h:
            phys_meta = json.load(h)
        # phys_ending is last element following a period
        phys_ending = phys_file.split(".")[-1]
        
        # Choose file opening function on the basis of whether file is gzippped
        if phys_ending == 'gz':
            opener = gzip.open 
        else:
            opener = open
            
        # Read Columns field of JSON file
        phys_dat = {k:[] for k in phys_meta['Columns']}
        
        # Append tab delimited phys_file to phys_dat
        with opener(phys_file, 'rt') as h:
            # for pl in h.readlines():
            for pl in h:
                pls = pl.split("\t")
                for k,v in zip(phys_meta['Columns'], pls):
                    phys_dat[k].append(float(v))
                    
        # Process StartTime is in JSON file
        if ('StartTime' in phys_meta and "StartTime" not in respiration_info):
            startTime = float(phys_meta["StartTime"])
            if (startTime > 0):
                print('***** WARNING: JSON file gives positive start time which is not currently handled')
                print('    Start time must be <= 0')
            else:
                respiration_info["StartTime"] = startTime            
                cardiac_info["StartTime"] = startTime            
                    
        print('phys_meta = ', phys_meta)
        # Read columns field from JSON data
        print('Read columns field from JSON data')
        for k in phys_meta['Columns']:
            phys_dat[k] = np.array(phys_dat[k])
            
            # Read respiratory component
            if k.lower() == 'respiratory' or k.lower() == 'respiration':
                # create peaks only if asked for    25 May 2021 [rickr]
                if respiration_out or rvt_out:
                   if not respiration_info["phys_fs"]:
                       respiration_info['phys_fs'] = phys_meta['SamplingFrequency']
                   respiration_file = None
                   phys_resp_dat = phys_dat[k]
            
            # Read cardiac component
            elif k.lower() == 'cardiac':
                # create peaks only if asked for    25 May 2021 [rickr]
                if cardiac_out != 0:
                   if not cardiac_info["phys_fs"]:
                       cardiac_info['phys_fs'] = phys_meta['SamplingFrequency']
                   cardiac_file = None
                   phys_cardiac_dat = phys_dat[k]
            else:
                print("** warning phys data contains column '%s', but\n" \
                      "   RetroTS only handles cardiac or respiratory data" % k)
    else:   # Not a JSON file
        if respiration_info["respiration_file"]:
            respiration_file = respiration_info["respiration_file"]
            phys_resp_dat = []
        if cardiac_info["cardiac_file"]:
            cardiac_file = cardiac_info["cardiac_file"]
            phys_cardiac_dat = []
            
    return respiration_file, phys_resp_dat, cardiac_file, phys_cardiac_dat

from numpy import zeros, size

def ouputInNimlFormat(physiologicalNoiseComponents, parameters):
    main_info = dict()
    main_info["rvt_out"] = parameters["rvt_out"]
    main_info["number_of_slices"] = parameters['-s']
    main_info["rvt_out"] = main_info["rvt_out"]
    main_info["prefix"] = parameters["prefix"]
    main_info["respiration_out"] = len(physiologicalNoiseComponents['respiratory_phases']) > 0
    main_info["cardiac_out"] = len(physiologicalNoiseComponents['cardiac_phases']) > 0
    
    respiration_info = phase_estimator(physiologicalNoiseComponents, 'r', main_info, parameters)
    cardiac_info = phase_estimator(physiologicalNoiseComponents, 'c', main_info, parameters)
    respiration_info["rvt_shifts"] = list(range(0, 21, 5))
    respiration_info["rvtrs_slc"] = np.zeros((len(respiration_info["rvt_shifts"]), len(respiration_info["time_series_time"])))

    n_n = 0
    n_r_v = 0
    n_r_p = 0
    n_e = 0

    if "time_series_time" in respiration_info:
        n_n = len(respiration_info["time_series_time"])
        n_r_p = size(respiration_info["phase_slice_reg"], 1)
        n_r_v = size(respiration_info["rvtrs_slc"], 0)

    if "time_series_time" in cardiac_info:  # must have cardiac_info
        n_n = len(
            cardiac_info["time_series_time"]
        )  # ok to overwrite len(respiration_info.tst), should be same.
        n_e = size(cardiac_info["phase_slice_reg"], 1)
    
    cnt = 0
    temp_y_axis = main_info["number_of_slices"] * (
        (main_info["rvt_out"]) * int(n_r_v)
        + (main_info["respiration_out"]) * int(n_r_p)
        + (main_info["cardiac_out"]) * int(n_e)
    )
    main_info["reml_out"] = zeros((n_n, temp_y_axis))

    head = (
        "<RetroTSout\n"
        'ni_type = "%d*double"\n'
        'ni_dimen = "%d"\n'
        'ColumnLabels = "'
        % (size(main_info["reml_out"], 1), size(main_info["reml_out"], 0))
    )
    tail = '"\n>'
    tailclose = "</RetroTSout>"

    label = head

    main_info["slice_major"] = 1
    main_info["reml_out"] = []
    if main_info["slice_major"] == 0:  # old approach, not handy for 3dREMLfit
        # RVT
        if main_info["rvt_out"] != 0:
            for j in range(0, size(respiration_info["rvtrs_slc"], 2)):
                for i in range(0, main_info["number_of_slices"]):
                    cnt += 1
                    main_info["reml_out"][:, cnt] = respiration_info["rvtrs_slc"][
                        :, j
                    ]  # same for each slice
                    label = "%s s%d.RVT%d ;" % (label, i, j)
        # Resp
        if main_info["respiration_out"] != 0:
            for j in range(0, size(respiration_info["phase_slice_reg"], 2)):
                for i in range(0, main_info["number_of_slices"]):
                    cnt += 1
                    main_info["reml_out"][:, cnt] = respiration_info["phase_slice_reg"][
                        :, j, i
                    ]
                    label = "%s s%d.Resp%d ;" % (label, i, j)
        # Card
        if main_info["Card_out"] != 0:
            for j in range(0, size(cardiac_info["phase_slice_reg"], 2)):
                for i in range(0, main_info["number_of_slices"]):
                    cnt += 1
                    main_info["reml_out"][:, cnt] = cardiac_info["phase_slice_reg"][
                        :, j, i
                    ]
                    label = "%s s%d.Card%d ;" % (label, i, j)
        fid = open(("%s.retrots.1D", main_info["prefix"]), "w")
    else:
        main_info["rvt_out"] = 0
        for i in range(0, main_info["number_of_slices"]):
            if main_info["rvt_out"] != 0:
                # RVT
                for j in range(0, np.shape(respiration_info["rvtrs_slc"])[0]):
                    cnt += 1
                    main_info["reml_out"].append(
                        respiration_info["rvtrs_slc"][j]
                    )  # same regressor for each slice
                    label = "%s s%d.RVT%d ;" % (label, i, j)
            if main_info["respiration_out"] != 0:
                # Resp
                for j in range(0, np.shape(respiration_info["phase_slice_reg"])[1]):
                    cnt += 1
                    main_info["reml_out"].append(
                        respiration_info["phase_slice_reg"][:, j, i]
                    )
                    label = "%s s%d.Resp%d ;" % (label, i, j)
            if main_info["cardiac_out"] != 0:
                # Card
                for j in range(0, np.shape(cardiac_info["phase_slice_reg"])[1]):
                    cnt += 1
                    main_info["reml_out"].append(
                        cardiac_info["phase_slice_reg"][:, j, i]
                    )
                    label = "%s s%d.Card%d ;" % (label, i, j)
        # fid = open(("%s.slibase.1D" % main_info["prefix"]), "w")

    # remove very last ';'
    label = label[1:-2]

    np.savetxt(
        "./%s.slibase.1D" % main_info["prefix"],
        np.column_stack(main_info["reml_out"]),
        fmt="%.4f",
        delimiter=" ",
        newline="\n",
        header=("%s%s" % (label, tail)),
        footer=("%s" % tailclose),
    )
    
def phase_estimator(physiologicalNoiseComponents, dataType, main_info, parameters):
    numTimeSteps = round(24199)
    phasee = dict()
    phasee["number_of_slices"] = 33
    phasee['slice_offset'] = parameters['slice_offset']
    phasee["t"] = np.zeros(numTimeSteps)
    for i in range(1,numTimeSteps): phasee["t"][i] = 2.0000e-02 * i
    
    if dataType == 'c':
        phasee["phase"] = physiologicalNoiseComponents['cardiac_phases']
    else:
        phasee["phase"] = physiologicalNoiseComponents['respiratory_phases']

    phasee["volume_tr"] = parameters['-TR']
    phasee["time_series_time"] = np.arange(
        0, (max(phasee["t"]) - 0.5 * phasee["volume_tr"]), phasee["volume_tr"]
    )
    if (max(phasee["t"]) - 0.5 * phasee["volume_tr"]) % phasee["volume_tr"] == 0:
        phasee["time_series_time"] = np.append(
            phasee["time_series_time"],
            [phasee["time_series_time"][-1] + phasee["volume_tr"]],
        )
    phasee["phase_slice"] = zeros(
        (len(phasee["time_series_time"]), phasee["number_of_slices"])
    )
    phasee["phase_slice_reg"] = zeros(
        (len(phasee["time_series_time"]), 4, phasee["number_of_slices"])
    )
    for i_slice in range(phasee["number_of_slices"]):
        tslc = phasee["time_series_time"] + phasee["slice_offset"][i_slice]
        for i in range(len(phasee["time_series_time"])):
            imin = np.argmin(abs(tslc[i] - phasee["t"]))
            phasee["phase_slice"][i, i_slice] = phasee["phase"][imin]
        # Make regressors for each slice
        phasee["phase_slice_reg"][:, 0, i_slice] = np.sin(
            phasee["phase_slice"][:, i_slice]
        )
        phasee["phase_slice_reg"][:, 1, i_slice] = np.cos(
            phasee["phase_slice"][:, i_slice]
        )
        phasee["phase_slice_reg"][:, 2, i_slice] = np.sin(
            2 * phasee["phase_slice"][:, i_slice]
        )
        phasee["phase_slice_reg"][:, 3, i_slice] = np.cos(
            2 * phasee["phase_slice"][:, i_slice]
        )
    
    return  phasee
    

