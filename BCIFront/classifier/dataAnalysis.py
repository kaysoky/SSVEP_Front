import sys
from naive import NaiveBayes
from naiveFormats import FormatJson
import matplotlib.pyplot as pl
import numpy as np
import matplotlib.mlab as mlab

def confusion(label, data):
    """ Shows a color coded confusion matrix

    Args:
        label: a list of labels for the data with the first being an empty
        string.
        data: an n element array holding arrays of size n

        [1 , 2] label=["", label 1, label 2]
        [2, 2 ] data = [[d11,d12],[d21,d22]]
    """
    fig = pl.figure()
    ax = fig.add_subplot(111)
    cax = ax.matshow(data)
    pl.title('Confusion matrix')
    ax.set_xticklabels(label)
    ax.set_yticklabels(label)
    fig.colorbar(cax)

def normDist(mean, sigma, left,right):
    x = np.linspace(left,right, 1000)
    pl.plot(x,mlab.normpdf(x,mean,sigma))

def plotDists(naive, labels):
    pl.figure()

    minMean = sys.maxint
    maxMean = -1*minMean - 1
    maxStd = maxMean

    toPlot = []

    for l in labels:
        for i in range(len(naive.mean[l])):
            mean = naive.mean[l][i][0]
            std = naive.stdv[l][i][0]
            toPlot.append((mean,std))

            if mean < minMean:
                minMean = mean

            if mean > maxMean:
                maxMean = mean

            if std > maxStd:
                maxStd = std

    l = 2*(minMean - maxStd)
    r = 2*(maxMean + maxStd)

    for m, s in toPlot:
        normDist(m,s,l,r)

formt = FormatJson(sys.argv[1])
naive = NaiveBayes(formt.data())
print "Total Accuracy (cross validate) = " +  str(naive.crossValidate(10))

labels = formt.channels()
counts = [[0]*len(labels) for i in range(len(labels))]

for label, data in formt.data():
    expectedChn, _ = naive.predict(data)

    # Confusion matrix
    correct = labels.index(label)
    actual = labels.index(expectedChn)
    counts[correct][actual] += 1

print counts
labels = [''] + labels
confusion(labels, counts)
plotDists(naive, labels[1:])
pl.show()

