'''
  @file perceptron.py
  @author Anand Soni

  Class to benchmark the mlpack Perceptron method.
'''

import os
import sys
import inspect
import numpy as np

# Import the util path, this method even works if the path contains symlinks to
# modules.
cmd_subfolder = os.path.realpath(os.path.abspath(os.path.join(
  os.path.split(inspect.getfile(inspect.currentframe()))[0], "../../util")))
if cmd_subfolder not in sys.path:
  sys.path.insert(0, cmd_subfolder)

#Import the metrics definitions path.
metrics_folder = os.path.realpath(os.path.abspath(os.path.join(
  os.path.split(inspect.getfile(inspect.currentframe()))[0], "../metrics")))
if metrics_folder not in sys.path:
  sys.path.insert(0, metrics_folder)

from log import *
from profiler import *
from definitions import *
from misc import *
import shlex

try:
  import subprocess32 as subprocess
except ImportError:
  import subprocess

import re
import collections

'''
This class implements the Perceptron Prediction benchmark.
'''
class PERCEPTRON(object):

  '''
  Create the Perceptron Prediction benchmark instance, show some
  informations and return the instance.

  @param dataset - Input dataset to perform Perceptron Prediction on.
  @param timeout - The time until the timeout. Default no timeout.
  @param path - Path to the mlpack executable.
  @param verbose - Display informational messages.
  '''
  def __init__(self, dataset, timeout=0, path=os.environ["BINPATH"],
      verbose=True, debug=os.environ["DEBUGBINPATH"]):
    self.verbose = verbose
    self.dataset = dataset
    self.path = path
    self.timeout = timeout
    self.debug = debug

    # Get description from executable.
    cmd = shlex.split(self.path + "mlpack_perceptron -h")
    try:
      s = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=False)
    except Exception as e:
      Log.Fatal("Could not execute command: " + str(cmd))
    else:
      # Use regular expression pattern to get the description.
      pattern = re.compile(br"""(.*?)Optional.*?options:""",
          re.VERBOSE|re.MULTILINE|re.DOTALL)

      match = pattern.match(s)
      if not match:
        Log.Warn("Can't parse description", self.verbose)
        description = ""
      else:
        description = match.group(1)

      self.description = description

  '''
  Destructor to clean up at the end. Use this method to remove created files.
  '''
  def __del__(self):
    Log.Info("Clean up.", self.verbose)
    filelist = ["gmon.out", "output.csv"]
    for f in filelist:
      if os.path.isfile(f):
        os.remove(f)

  '''
  Given an input dict of options, convert it to a string that the program can
  use.
  '''
  def OptionsToStr(self, options):
    optionsStr = ""
    if "max_iterations" in options:
      optionsStr = "-n " + str(options.pop("max_iterations"))
    if len(options) > 0:
      Log.Fatal("Unknown parameters:" + str(options))
      raise Exception("unknown parameters")

    return optionsStr

  '''
  Run valgrind massif profiler on the Perceptron Prediction
  method. If the method has been successfully completed the report is saved in
  the specified file.

  @param options - Extra options for the method.
  @param fileName - The name of the massif output file.
  @param massifOptions - Extra massif options.
  @return Returns False if the method was not successful, if the method was
  successful save the report file in the specified file.
  '''
  def RunMemory(self, options, fileName, massifOptions="--depth=2"):
    Log.Info("Perform Perceptron Memory Profiling.", self.verbose)

    # If the dataset contains two files then the second file is the test file.
    # In this case we add this to the command line.
    if len(self.dataset) >= 2:
      cmd = shlex.split(self.debug + "mlpack_perceptron -t " + self.dataset[0] +
          " -T " + self.dataset[1] + " -v " + self.OptionsToStr(options))
    else:
      Log.Fatal("This method requires atleast two datasets.")

    return Profiler.MassifMemoryUsage(cmd, fileName, self.timeout, massifOptions)

  '''
  Perform Perceptron Prediction. If the method has been
  successfully completed return the elapsed time in seconds.

  @param options - Extra options for the method.
  @return - Elapsed time in seconds or a negative value if the method was not
  successful.
  '''
  def RunMetrics(self, options):
    Log.Info("Perform Perceptron Prediction.", self.verbose)

    # If the dataset contains two files then the second file is the labels file.
    # In this case we add this to the command line.
    if len(self.dataset) >= 2:
      cmd = shlex.split(self.path + "mlpack_perceptron -t " + self.dataset[0]
          + " -T " + self.dataset[1] + " -v " + self.OptionsToStr(options)
          + " -o output.csv")
    else:
      Log.Fatal("This method requires atleast two datasets.")

    # Run command with the nessecary arguments and return its output as a byte
    # string. We have untrusted input so we disable all shell based features.
    try:
      s = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=False,
          timeout=self.timeout)
    except subprocess.TimeoutExpired as e:
      Log.Warn(str(e))
      return -2
    except Exception as e:
      Log.Fatal("Could not execute command: " + str(cmd))
      return -1

    # Datastructure to store the results.
    metrics = {}

    # Parse data: runtime.
    timer = self.parseTimer(s)

    if timer != -1:
      metrics['Runtime'] = timer.total_time - timer.saving_data - timer.loading_data
      metrics['Training'] = timer.training
      metrics['Testing'] = timer.testing

      Log.Info(("total time: %fs" % (metrics['Runtime'])), self.verbose)

    if len(self.dataset) >= 3 and CheckFileAvailable('output.csv'):
      testData = LoadDataset(self.dataset[1])
      truelabels = LoadDataset(self.dataset[2])
      predictedlabels = LoadDataset("output.csv")

      confusionMatrix = Metrics.ConfusionMatrix(truelabels, predictedlabels)
      metrics['ACC'] = Metrics.AverageAccuracy(confusionMatrix)
      metrics['MCC'] = Metrics.MCCMultiClass(confusionMatrix)
      metrics['Precision'] = Metrics.AvgPrecision(confusionMatrix)
      metrics['Recall'] = Metrics.AvgRecall(confusionMatrix)
      metrics['MSE'] = Metrics.SimpleMeanSquaredError(truelabels, predictedlabels)
      return metrics

    return metrics

  '''
  Parse the timer data form a given string.

  @param data - String to parse timer data from.
  @return - Namedtuple that contains the timer data or -1 in case of an error.
  '''
  def parseTimer(self, data):
    # Compile the regular expression pattern into a regular expression object to
    # parse the timer data.
    pattern = re.compile(br"""
        .*?loading_data: (?P<loading_data>.*?)s.*?
        .*?saving_data: (?P<saving_data>.*?)s.*?
        .*?testing: (?P<testing>.*?)s.*?
        .*?total_time: (?P<total_time>.*?)s.*?
        .*?training: (?P<training>.*?)s.*?
        """, re.VERBOSE|re.MULTILINE|re.DOTALL)

    match = pattern.match(data)
    if not match:
      Log.Fatal("Can't parse the data: wrong format")
      return -1
    else:
      # Create a namedtuple and return the timer data.
      timer = collections.namedtuple('timer', ["loading_data",
                                               "saving_data",
                                               "testing",
                                               "total_time",
                                               "training"])
      return timer(float(match.group("loading_data")),
                   float(match.group("saving_data")),
                   float(match.group("testing")),
                   float(match.group("total_time")),
                   float(match.group("training")))
