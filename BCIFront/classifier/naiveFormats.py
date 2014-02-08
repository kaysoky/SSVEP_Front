import json
import scipy.io

class FormatMat:
    """ Takes a matlab training file and processes it in a way the NaiveBayes
        classifier can use
    """

    def __init__(self, trainingFile, samples=1):
        """ Given a path to a matlab file, it will do post processing and place
        labelled data in an instance variable for later access.

        Args: trainingFile is the path to the *.mat file
        """
        self.formatedList = []
        matFile = scipy.io.loadmat(trainingFile)

        # Each index contains a unique label and the associated data
        # dataList[class][0=label, 1=data][frequency Hz][FFT chunks][Trial #]
        dataList = matFile["Transformed"].tolist()[0]

        for clss in dataList:
            label = str(clss[0][0])
            data = clss[1]

            # Need to parse label to determine frequency of interest
            # Removing " Hz" from end
            freq = int(label[:-3:1])

            # Generate ("label", [fft0,..., fftN]) for each trial
            trials = len(data[1][1])

            # Sample number of fft data points from each frequency window
            for j in range(trials):
                for i in filter(lambda x: x % samples == 0, range(len(data[freq]) - samples + 1)):

                    # Makes a list of sample data points * number of frequencies of interest
                    merge = []

                    for f in range(freq - 10, freq + 10):
                        for k in range(i, i+samples):
                            merge.append(data[f][k][j])

                    self.formatedList.append((label, merge))

            # The full frequency window for each data point
            #for i in range(trials):
                #trialData = []

                #for j in range(freq-10,freq+10):
                    #for fft in data[j]:
                        #trialData.append(fft[i])

                ## Remove the first value which is the start of the trial
                #self.formatedList.append((label, trialData))

    def data(self):
        """ Returns the formated data which is stored in a list holding
        tuples of label to [data]
        """
        return list(self.formatedList)

class FormatJson:
    """ Takes a json training file that was generated from the bci gui application in this
    package and processes it in a way the NaiveBayes classifier can use.
    """

    def __init__(self, trainingFile, samples=1, loadDict=False):
        """ Given a path to a json file, it will do post processing and place
        labelled data in an instance variable for later access.

        Args:
            trainingFile: the path to the *.json file
            samples: the number of values for each frequency in each label data pair
                    This determines the dimensionality of the classifier
            loadDict: if load dict is set to true it treats trainingFile as a python dictionary
            and forgoes loading a json file

        Throws: Exception if file cannot be opened
        """
        self.chans = set()
        jData = self.loadJson(trainingFile) if not loadDict else trainingFile

        self.freqList = jData["Collected Channels"]
        self.formatedList = []

        # Trial is the trial number and tData is the associated data
        for trial, tData in jData["Data"].items():

            # cData holds the data for EMD, Noise and raw FFT
            for channel, cData in tData.items():
                self.chans.add(channel)

                # Dictionary of "[0-128] Hz" -> [data]
                # Choices are "EMD", "EMD Noise" and "Raw FFT"
                emd = cData["Raw FFT"]
                #labelChannel = int(channel[:-3])

                # This gives you a list containing indexes separated by samples. If samples = 4
                # This list could be [0,4,8] for a list of size 12
                for i in filter(lambda x: x % samples == 0, range(len(emd["0"]) - samples + 1)):

                    # Makes a list of sample data points * number of frequencies of interest
                    merge = []

                    for f in self.harmonicRange(self.freqList, 0, 2):
                        merge.extend(emd[str(f)][i:i+samples])

                    self.formatedList.append((channel, merge))

    @classmethod
    def harmonicRange(cls, hzList, numHarms, epsilon):
        """ Generates a list of frequencies that are the elements specified in the hzList
            and its harmonics up to numHarms*freq out and the hz epsilon around
        """
        hz = []

        for h in hzList:
            for c in [h*i for i in range(1,numHarms+2)]:
                hz.extend([x for x in range(c - epsilon, c+epsilon)])

        return hz

    def formatFrequencies(self, freqDict, samples=1):
        """ Takes a dictionary of frequencies (str) to arrays of values and creates an
        array of values representing features of the classifier """

        # Makes a list of sample data points * number of frequencies of interest
        merge = []

        for f in self.harmonicRange(self.freqList, 0, 2):
            merge.extend(freqDict[str(f)][0:samples])

        return merge

    @classmethod
    def loadJson(cls, trainingFile):
        """ Given a path to a json file, it will attempt to load it as a dictionary

        Args:
            trainingFile: the path to the *.json file

        Throws: Exception if file cannot be opened
        """
        # Try to open file
        try:
            jFile = open(trainingFile, "r")
        except IOError as e:
            raise Exception("Couldn't open file", e)

        # Try to parse json file
        try:
            return json.load(jFile)
        except ValueError as e:
            raise Exception("Couldnt parse json file!", e)

    def data(self):
        """ Returns the formated data which is stored in a list holding
        tuples of label to [data]
        """
        return list(self.formatedList)

    def channels(self):
        """ Returns a set of the unique channels """
        return list(self.chans)
