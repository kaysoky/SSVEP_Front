import socket
import re
import json

class bciComms():
    @classmethod
    def bciConnection(cls, ip, port, toSend, pipe):
        """ Intended to be run on its own thread or process to connect and receive
        messages from bci2000.

        Args:
            ip, port: specify the BCI2000 app connector output
            toSend: a process safe boolean that indicate when to send data
            pipe: a pipe in which to write the data to when toSend is true
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((ip, port))
        sock.listen(1)

        # Preflight check. BCI2000 opens and then closes the socket
        conn, addr = sock.accept()
        conn.close()

        print ip, port

        while True:
            conn, addr = sock.accept()
            i = 0

            while True:
                data = conn.recv(65535)
                if not data: break

                #i += 1
                #if i < 10:
                    #print data

                # toSend is a process-safe boolean value
                if toSend.value:
                    pipe.send(data)

            conn.close()

    @classmethod
    def determineEndRegex(cls, pipe):
        first =  re.compile(r"Signal\(([0-9]+),([0-9]+)\)")
        last = ""
        lastFull = True
        
        seenFirst = False
        maxChan = -1
        maxSig = -1

        while True:
            data = pipe.recv()

            for data, full in bciComms.tcpYielder(data):
                if not full:
                    last += data
                    lastFull = False
                    continue
                elif full and not lastFull:
                    lastFull = True
                    data = last + data
                    last = ""

                match = first.match(data)
                if match:
                    chan = int(match.group(1))
                    sig = int(match.group(2))
                    
                    if seenFirst and chan == 0 and sig == 0:
                        return "Signal\("+str(maxChan)+","+str(maxSig)+"\)"
                    
                    if chan == 0 and sig == 0:
                        seenFirst = True

                    if chan > maxChan:
                        maxChan = chan

                    if sig > maxSig:
                        maxSig = sig


    @classmethod
    def processTrainData(cls, trainData, freqList, fileHandle=None):
        """ Does post processing on the training data dict and saves it to a json file.
        Also returns the python dictionary

        Args:
            trainData: a dictionary containing trial numbers mapping to a dictionary that has
            freqList: the list of frequencies collected on
            channels to another dict mapping signal type (EMD/FFT)
            to an array of collected data ({1:{"12 Hz": "EMD": [1,2,3], ...}})

            fileHandle: an open file handle to save the json file to. If not set, the json file
            is not saved
        """
        js= {}


        for trial in trainData.keys():
            js[trial] = {}
            for channel in trainData[trial].keys():
                # Data contains every udp packet received while collecting for
                # the respective trial/channel
                data = trainData[trial][channel]
                js[trial][channel] = bciComms.rawToDict(data)

        js = {"Data": js}
        js["Collected Channels"] = freqList

        # Prints to file and returns the dict
        if fileHandle:
            json.dump(js, fileHandle, indent=4, separators=(',', ': '))

        return js

    @classmethod
    def rawToDict(cls, data):
        """ Takes an array of a period of BCI2000 data and decomposes it into
        a dictionary of channels and signals

        Args:
            data: array of BCI2000 app connector messages

        Return: a dictionary of {"EMD":{"0": [data], "1":[data]..}...}"""

        r = re.compile("Signal\(([0-9]+),([0-9]+)\)[\s]([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)")
        extracted = {}

        for sig in data:
            m = r.match(sig)
            if not m: continue

            g = m.groups()
            s = str(g[0]) # Signal
            c = str(g[1]) # Channel
            v = float(g[2]) # Value

            # Convert Signal to readable name
            s = {"0": "Raw FFT"}.get(s)

            if s == None: continue

            # Initializes values if it is the first time
            if not extracted.has_key(s):
                extracted[s] = {}

            if not extracted[s].has_key(c):
                extracted[s][c] = []

            extracted[s][c].append(v)

        return extracted

    @classmethod
    def collectData(cls, pipe, duration, headRegex, endRegex, retQueue, lastStamp):
        """ Collects data from the pipe for a certain duration. Returns the last time
        stamp of the data collected

        Args:
            pipe: a pipe to read BCI2000 data from
            duration: The number of seconds to read data
            headRegex: A regex string that contains a group with the SourceTime
            time stamp in it. Used to keep track of elapsed time on the BCI2000
            machine collecting data
            endRegex: Regex string matching the end of a grouping of packets used to
            ensure all data is received
            retQueue: A process safe queue in which to store the collected data
            which is just a list of the received data
            lastStamp: The last time stamp received before the collection starts. An int
        """
        numPackets = int(duration / .5)
        epsilon = 25
        duration *= 1000 # Convert from seconds to milliseconds
        res = []
        hcomp = re.compile(headRegex)
        fcomp = re.compile(endRegex)
        elapsed = 0.0
        lastFull = True
        last = ""
        fullPacket = False
        count = 0

        # while (elapsed < duration - epsilon) or not fullPacket:
        while count < numPackets or not fullPacket:

            data = pipe.recv()
            fullPacket = False

            for data, full in bciComms.tcpYielder(data):
                if not full:
                    last += data
                    lastFull = False
                    continue
                elif full and not lastFull:
                    lastFull = True
                    data = last + data
                    last = ""

                # Add full data to list
                res.append(data+"\n")

                # Checking if all data is received
                if fcomp.match(data):
                    fullPacket = True

                # Updating time stamps
                hmatch = hcomp.match(data)
                if hmatch:
                    stamp = int(hmatch.group(1))
                    count += 1

                    if lastStamp == None:
                        lastStamp = stamp
                    else:
                        temp = bciComms.timeDiff(lastStamp, stamp)
                        elapsed += temp
                        lastStamp = stamp

        retQueue.put(res)
        return lastStamp

    @classmethod
    def timeDiff(cls, first, second):
        """ Calculates the ms difference between the two time stamps.
            The range is from 0-65536ms

            Args:
                first/second: the two integer time stamps to find the elapsed
                time between

            Return: Elapsed time from first to second
        """
        diff = second - first
        return diff if diff > 0 else diff + 65536

    @classmethod
    def discardTill(cls, pipe, endRegex, headRegex):
        """ Reads from the pipe until the result matches the regex.

        Return: The value in the first group of headRegex

        Args:
            pipe: A Connection Object that has a poll and recv method
            endRegex: A string representing a regular expression, when the regular
            expression is matched, the method returns.
            headRegex: A regex string with a grouping. When this string is matched
            the value is saved and when both a value of the headRegex has been seen
            and the endRegex is observed, that value is returned
        """
        comp = re.compile(endRegex)
        hComp = re.compile(headRegex)
        lastFull = True
        last = ""
        stamp = None


        while True:
            data = pipe.recv()

            for data, full in bciComms.tcpYielder(data):
                if not full:
                    last += data
                    lastFull = False
                    continue
                elif full and not lastFull:
                    lastFull = True
                    data = last + data
                    last = ""

                hmatch = hComp.match(data)
                if hmatch:
                    stamp = hmatch.group(1)

                if comp.match(data) and stamp:
                    return stamp



    @classmethod
    def tcpYielder(cls, packet):
        """ Given a new line separated tcp packet it yields the data until a new line.
        If the data is not complete it yields all the packet contains and false

        Args:
            packet: The full '\n' separated packet

        Yield: string, bool
            where the string is data between new line separators or the last of the packet
            and a boolean saying whether it is the full data
        """
        builder = ""

        for char in packet:
            if char == '\n':
                temp = builder
                builder = ""
                yield temp, True
            else:
                builder += char

        yield builder, False

