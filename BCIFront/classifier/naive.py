import scipy.io
import numpy
import scipy.stats
import sys
from naiveFormats import FormatJson

class NaiveBayes:

    # Take list of [tuple ("class", [data0, data1,...,dataN])]
    def __init__(self, trainingData):
        NaiveBayes.checkTrainData(trainingData)

        self.trainingData = trainingData
        self.predictThreshold = .95
        self.priors = {}
        self.num= len(trainingData[0][1])
        self.mean = {}
        self.stdv = {}

        for (label, data) in trainingData:
            # Build up the priors by counting occurances of each class
            if self.priors.has_key(label):
                self.priors[label] += 1
                [self.mean[label][i].append(data[i]) for i in range(self.num)]

                # builds up an array of arrays containing each value for the
                # feature
                [self.stdv[label][i].append(data[i]) for i in range(self.num)]
            else:
                self.priors[label] = 1
                self.mean[label] = [[i] for i in data]
                self.stdv[label] = [[i] for i in data]


        # Post processing
        for label in self.priors.keys():
            # Calculate the prior probability
            self.priors[label] = self.priors[label] / float(len(trainingData))

            # REMOVE DATA ABOVE x STD DEVIATIONS FROM MEAN AND RECALCULATE
            for i,l in enumerate(self.mean[label]):
                std = numpy.std(l)
                mean = numpy.mean(l)
                self.mean[label][i] = filter(lambda y: y <= mean+3*std or y >= mean-3*std, l)

                self.stdv[label][i] = [numpy.std(self.mean[label][i])]
                self.mean[label][i] = [numpy.mean(self.mean[label][i])]


    @classmethod
    def checkTrainData(cls, data):
        """ Checks the data to ensure it is properly formated. This means it is a list
        containing tuples of strings to lists of data all containing the same number of
        elements """

        if data == None or len(data) == 0:
            raise Exception("No data")

        if type(data[0]) != tuple:
            raise Exception("Not a list of tuples")

        if len(data[0]) != 2 and type(data[0][0]) != str and type(data[0][1]) != list:
            raise Exception("Not a tuple of (String, [data])")

        length = len(data[0][1])

        for tup in data:
            if len(tup) != 2 and type(tup[0]) != str and type(tup[1]) != list:
                raise Exception("Not a tuple of (String, [data])")

            if len(tup[1]) != length:
                raise Exception("Not all elements have the same amount of data")


    def predict(self, features):
        if len(features) != self.num:
            raise Exception("Wrong number of features. Can't predict")

        probs = self.priors.copy()

        for label in probs.keys():
            probs[label] = numpy.log(probs[label])

            for i in range(self.num):
                curProb = scipy.stats.norm.pdf(features[i], self.mean[label][i],
                                               self.stdv[label][i])

                if curProb <= 0:
                    print "Not possible for pdf to return -> " + str(curProb)
                    continue
                probs[label] += numpy.log(curProb)

        norm = None
        results = [(probs[l], l) for l in probs.keys()]
        try:
            probs = numpy.array([e[0] for e in results])
            zeroize = numpy.mean(probs)
            probs = probs + zeroize # Shift means of logged elements to zero
            probs = numpy.exp(probs)

            # Does not make sense to remove because then you dont know what
            # classes exist anymore
            # probs = filter(lambda x: float(x) != float('inf'), probs) # Get rid of super large values after exponentiation
            norm = probs / sum(probs)
        except Exception:
            norm = numpy.array([0])

        # "class", dict("class", probability)]
        classProbs = map(lambda (a,b): (a,b[0]), zip([r[1] for r in results], norm.tolist()))
        return max(classProbs, key=lambda x: x[1])[0], dict(classProbs)

    @classmethod
    def kFoldGen(cls, X, K):
        for k in range(K):
            training = [x for i, x in enumerate(X) if i % K != k]
            validation = [x for i, x in enumerate(X) if i % K == k]
            yield training, validation


    # Data is the formated training data and k is the chunks to break it into
    def crossValidate(self, K):
        correct = 0
        total = 0

        for train, val in NaiveBayes.kFoldGen(self.trainingData, K):
            classy = NaiveBayes(train)

            for trial in val:
                total += 1
                res, _ = classy.predict(trial[1])

                if res == trial[0]:
                    correct += 1

        perc = correct / float(total) * 100

        return perc


if __name__ == '__main__':
    if (len(sys.argv) < 2):
        sys.exit(0)

    formated = FormatJson(sys.argv[1])
    classy = NaiveBayes(formated.formatedList)
    perc = classy.crossValidate(10)
    print sys.argv[1]
    print "Total Accuracy = " +  str(perc)

    #test(classy, formated.formatedList)
