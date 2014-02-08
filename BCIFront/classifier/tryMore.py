from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier #, AdaBoostClassifier
from sklearn.naive_bayes import GaussianNB, MultinomialNB
from sklearn.lda import LDA
from sklearn.qda import QDA
from sklearn.cross_validation import train_test_split
import numpy as np
from naiveFormats import FormatJson
import sys

names = ["Nearest Neighbors", "Linear SVM", "RBF SVM", "Decision Tree",
         "Random Forest", "Naive Bayes", "MultinomialNB", "LDA", "QDA"]
classifiers = [
    KNeighborsClassifier(3),
    SVC(kernel="linear", C=0.025),
    SVC(gamma=2, C=1),
    DecisionTreeClassifier(max_depth=5),
    RandomForestClassifier(max_depth=5, n_estimators=10, max_features=1),
    #AdaBoostClassifier(),
    GaussianNB(),
    MultinomialNB(1.0, True),
    LDA(),
    QDA()]

formater = FormatJson(sys.argv[1])
data = formater.data()

x = []
y = []

for l, d in data:
    x.append(d)

    if l == "17 Hz":
        y.append(1)
    else:
        y.append(0)

X = np.asarray(x)
Y = np.asarray(y)

for name, clf in zip(names, classifiers):
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=.2)
    clf.fit(X_train, y_train)
    score = clf.score(X_test, y_test)

    print name, ": " , score
