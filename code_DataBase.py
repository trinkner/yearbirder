# import basic Python libraries
import os
import csv
import zipfile
import io
import sys
from copy import deepcopy
from collections import defaultdict
import datetime
import code_Filter
import json
import piexif
from math import floor
from natsort import natsorted

from PyQt5.QtWidgets import (
    QApplication,
    QMessageBox
    )


#routine to open helper files (json, csv, etc.) in fashion compatible with PyInstaller for when code is bundled into an app.
def resource_path(filename):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, filename)
    return filename

    
class DataBase():

    # this is the class that will store all our data and the data-seeking logic 
    
    def __init__(self):
        self.allSpeciesList = []
        self.familyList = []
        self.orderList = []
        self.masterFamilyOrderList = []
        self.masterLocationList = []
        self.regionList = []
        self.countryList = []
        self.stateList = []
        self.countyList = []
        self.locationList = []
        self.validPhotoSpecies = []
        self.cameraList = []
        self.lensList = []
        self.shutterSpeedList = []
        self.apertureList = []
        self.focalLengthList=[]
        self.isoList = []
        self.sightingList = []
        self.eBirdFileOpenFlag = False
        self.photoDataFileOpenFlag = False
        self.photosNeedSaving = False
        self.countryStateCodeFileFound = False
        self.speciesDict = defaultdict()
        self.yearDict = defaultdict()
        self.monthDict = defaultdict()
        self.dateDict = defaultdict()
        self.countryDict = defaultdict()
        self.stateDict = defaultdict()
        self.countyDict = defaultdict()
        self.locationDict = defaultdict()
        self.checklistDict = defaultdict()
        self.familySpeciesDict = defaultdict()
        self.orderSpeciesDict = defaultdict()
        self.bblCodeDict = defaultdict()
        self.photoDataFile = ""
        self.startupFolder = ""
        self.monthNameDict = ({
            "01":"Jan",
            "02":"Feb",
            "03":"Mar",
            "04":"Apr",
            "05":"May",
            "06":"Jun",
            "07":"Jul",
            "08":"Aug",
            "09":"Sep",
            "10":"Oct",
            "11":"Nov",
            "12":"Dec"
            })
        self.monthNumberDict = ({
            "Jan":"01",
            "Feb":"02",
            "Mar":"03",
            "Apr":"04",
            "May":"05",
            "Jun":"06",
            "Jul":"07",
            "Aug":"08",
            "Sep":"09",
            "Oct":"10",
            "Nov":"11",
            "Dec":"12"
            })            
        self.regionNameDict = ({
            "ABA":"ABA Area",
            "AOU":"AOU Area",
            "NAM":"North America",
            "SAM":"South America",
            "AFR":"Africa",
            "EUR":"Europe",
            "ASI":"Asia",
            "SPO":"South Polar",
            "WHE":"Western Hemisphere",
            "EHE":"Eastern Hemisphere",
            "WIN":"West Indies",
            "CAM":"Central America",
            "USL":"USA Lower 48",
            "AUA":"Australasia (ABA)",
            "AUE":"Australasia (eBird)",
            "AUS":"Australia and Territories"
            }) 
        self.regionCodeDict = ({
            "ABA Area":"ABA",
            "AOU Area":"AOU",
            "North America":"NAM",
            "South America":"SAM",
            "Africa":"AFR",
            "Europe":"EUR",
            "Asia":"ASI",
            "South Polar":"SPO",
            "Western Hemisphere":"WHE",
            "Eastern Hemisphere":"EHE",
            "West Indies":"WIN",
            "Central America":"CAM",
            "USA Lower 48":"USL",
            "Australasia (ABA)":"AUA",
            "Australasia (eBird)":"AUE",
            "Australia and Territories":"AUS"
            }) 

        # Use resource_path helper routine (in module, below) to open files in way safe for PyInstaller app bundle
        # Load JSON files using resource_path
        stateJsonFile   = resource_path("us-states.json")
        countyJsonFile  = resource_path("us-counties-lower48.json")
        countryJsonFile = resource_path("world-countries.json")
        
        # load us-states json shape file for later use with choropleths
        with open(stateJsonFile) as f:
            self.state_geo = json.loads(f.read())

        # load us-counties-lower48 json shape file for later use with choropleths
        with open(countyJsonFile) as f:
            self.county_geo = json.loads(f.read())
        
        # save county code data for easy lookup when processing eBird data file
        self.countyCodeDict = defaultdict()
        self.countyCodeList = set()
        for c in self.county_geo["features"]:
            
            # save master list of all US county codes for use with choropleths
            self.countyCodeList.add(c["id"])

            if c["properties"]["name"] not in self.countyCodeDict.keys():
                self.countyCodeDict[c["properties"]["name"]] = [[c["id"],c["properties"]["state"]]]
                
            else:    
                self.countyCodeDict[c["properties"]["name"]].append([c["id"],c["properties"]["state"]])
        
        # load world-countries json shape file for later use with choropleths
        with open(countryJsonFile) as f:
            self.country_geo = json.loads(f.read())
        

    def matchPhoto(self, file):
        
        # method to suggest a commonName, date, time, and location for a photo
        
        # get just the filename portion from the full-path filename
        fileName = os.path.basename(file)
        
        # get the EXIF data from the file, if possible
        try:
            photoExif = piexif.load(file)
        except:
            photoExif = ""
        
        # get photo date from EXIF
        try:
            photoDateTime = photoExif["Exif"][piexif.ExifIFD.DateTimeOriginal].decode("utf-8")
            
            # parse EXIF data for date/time components
            photoDate = photoDateTime[0:4] + "-" + photoDateTime[5:7] + "-" + photoDateTime[8:10]
            photoTime = photoDateTime[11:13] + ":" + photoDateTime[14:16]
        except:
            photoDate = ""
            photoTime = ""
        
        # use date and time to select a sighting location from db
        filter = code_Filter.Filter()
        filter.setStartDate(photoDate)
        filter.setEndDate(photoDate)
        filter.setTime(photoTime)
        locations = self.GetLocations(filter, "OnlyLocations")
        
        # if we find only one location, return it
        if len(locations) == 1:
            photoLocation = locations[0]
        
        else:
            photoLocation = ""
                    
        # if no single location matched the photo, but we have a date, find which checklist is closest to the photo datetime    
        if photoLocation == "" and photoDate != "":
            # try finding a checklist with the right date
            filter = code_Filter.Filter()
            filter.setStartDate(photoDate)
            filter.setEndDate(photoDate)
            locations = self.GetLocations(filter, "OnlyLocations")
                        
            if len(locations) == 1:
                photoLocation = locations[0]
                possibleStartTimes = self.GetStartTimes(filter)
                if len(possibleStartTimes) > 0:
                    photoTime = possibleStartTimes[0]
            
            # if more than one location was found, find which was visited closest to the photo time 
            elif len(locations) > 1 and photoTime != "":                
                filter = code_Filter.Filter()
                filter.setStartDate(photoDate)
                filter.setEndDate(photoDate)
                checklists = self.GetChecklists(filter)
                # create list to store location and checklist time for closest one to our photo's datetime
                # third list entry starts with total minutes in a day (most gap possible)
                checklistTimeDifference = ["", "", 24 * 60]
                photoMinutesSinceMidnight = 60 * int(photoTime[0:2]) + int(photoTime[3:5])
                
                for c in checklists:
                    
                    checklistTime = c[5]
                    
                    checklistDuration = c[7]
                    if checklistDuration == "":
                        checklistDuration = "0"
                    
                    checklistStartMinSinceMidnight = 60 * int(checklistTime[0:2]) + int(checklistTime[3:5])
                    checklistEndMinSinceMidnight = checklistStartMinSinceMidnight + int(checklistDuration)
                    
                    # check if this checklist's time is closer to our photo's time than any other checklist looped through so far
                    # If so, save its data into checklistTimeDifference
                    if abs(photoMinutesSinceMidnight - checklistStartMinSinceMidnight) < checklistTimeDifference[2]:
                        checklistTimeDifference = [c[3], c[5], abs(photoMinutesSinceMidnight - checklistStartMinSinceMidnight)]
                    
                    if abs(photoMinutesSinceMidnight - checklistEndMinSinceMidnight) < checklistTimeDifference[2]:
                        checklistTimeDifference = [c[3], c[5], abs(photoMinutesSinceMidnight - checklistEndMinSinceMidnight)]                    
                        
                if checklistTimeDifference[0] != "":
                    photoLocation = checklistTimeDifference[0]
                    photoTime = checklistTimeDifference[1]
                    
                        
        # try to use file name to match commonName using date, time, and location found already
        if photoLocation != "" and photoDate != "" and photoTime != "":
            filter = code_Filter.Filter()
            filter.setLocationType("Location")
            filter.setLocationName(photoLocation)
            filter.setStartDate(photoDate)
            filter.setEndDate(photoDate)
            filter.setTime(photoTime)
            possibleCommonNames = self.GetSpecies(filter)
             
            # set up translation table to remove inconvenient characters from file name 
            # and possiblecommonNames    
            translation_table = dict.fromkeys(map(ord, "0123456789-' "), None)                    
            
            # make file name lower case and remove inconvenient characters
            fileName = str(fileName)
            fileName = fileName.lower()
            fileName = fileName.translate(translation_table)
            
            # create list to store most likely commonName and number of matching characters
            mostLikelyCommonName = [0, "", ""]
            
            # cycle through possibleCommonNames, testing them piece by piece
            # to find which matches the most number of consecutive characters
            
            for pcn in possibleCommonNames:
                lowerCasePcn = pcn.lower()
                lowerCasePcn = lowerCasePcn.translate(translation_table)
                possibleCommonNameLength = len(lowerCasePcn)
                for i in range(possibleCommonNameLength):
                    for ii in range(i + 1, possibleCommonNameLength + 1):
                        if lowerCasePcn[i:ii] in fileName:
                            if len(lowerCasePcn[i:ii]) > mostLikelyCommonName[0]:
                                mostLikelyCommonName[0] = len(lowerCasePcn[i:ii])
                                mostLikelyCommonName[1] = pcn
                                mostLikelyCommonName[2] = lowerCasePcn[i:ii]
                                if len(lowerCasePcn[i:ii]) == len(lowerCasePcn):
                                    # matched the full possible name, so stop checking
                                    break
            
            photoCommonName = mostLikelyCommonName[1]
                        
        else:
            photoCommonName = ""
        
        photoMatchData = {}
        photoMatchData["photoLocation"] = photoLocation
        photoMatchData["photoDate"] = photoDate
        photoMatchData["photoTime"] = photoTime
        photoMatchData["photoCommonName"] = photoCommonName
            
        return(photoMatchData)


    def removeUnfoundPhotos(self):

        count = 0
        
        # method to remove photos from database
        # create filter with no settings to retrieve every photo in db
        filter = code_Filter.Filter()
        
        # get all sightings with photos
        sightings = self.GetSightingsWithPhotos(filter)

        for s in sightings:
            for p in s["photos"]:
                if not os.path.isfile(p):
                    s["photos"].remove(p)
                    count += 1

        # return the number of removed files
        return(count)
    

    def removePhotoFromDatabase(self, location, date, time, commonName, photoFileName):

        # method to remove photos from database
        filter = code_Filter.Filter()
        filter.setLocationType("Location")
        filter.setLocationName(location)
        if date != "":
            filter.setStartDate(date)
            filter.setEndDate(date)
        if time != "":
            filter.setTime(time)
        filter.setSpeciesName(commonName)
        
        # get sightings that match the filter. Should only be a single sighting.
        sightings = self.GetSightingsWithPhotos(filter)

        for s in sightings:
            if "photos" in s.keys():
                for p in s["photos"]:
                    if p["fileName"] == photoFileName:
                        s["photos"].remove(p)

            # if we've removed all the photos for this sighting, we need to remove the "photos" entry in the dict
            if len(s["photos"]) == 0:
                s.pop("photos", None)
                

    def getPhotoData(self, fileName):
        
        photoData = {}
                 
        # try to get EXIF data
 
        try:
            exif_dict = piexif.load(fileName)
        except:
            exif_dict = ""
             
        try:
            photoCamera = exif_dict["0th"][piexif.ImageIFD.Model].decode("utf-8")
        except:
            photoCamera = ""
        try:
            photoLens = exif_dict["Exif"][piexif.ExifIFD.LensModel].decode("utf-8")
        except:
            photoLens = ""
        try:        
            shutterSpeedFraction = exif_dict["Exif"][piexif.ExifIFD.ExposureTime]
            photoShutterSpeed = floor(shutterSpeedFraction[1]/shutterSpeedFraction[0])
            photoShutterSpeed = "1/" + str(photoShutterSpeed)
        except:
            photoShutterSpeed = ""
        try:
            photoAperture = exif_dict["Exif"][piexif.ExifIFD.FNumber]
            photoAperture = round(photoAperture[0] / photoAperture[1], 1)
        except:
            photoAperture = ""                    
        try:
            photoISO = exif_dict["Exif"][piexif.ExifIFD.ISOSpeedRatings]
        except:
            photoISO = ""                
        try:
            photoFocalLength = exif_dict["Exif"][piexif.ExifIFD.FocalLength]
            photoFocalLength = floor(photoFocalLength[0] / photoFocalLength[1])
            photoFocalLength = str(photoFocalLength) + " mm"                    
        except:
            photoFocalLength = ""  
        
        # get photo date from EXIF
        try:
            photoDateTime = exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal].decode("utf-8")
            
            #parse EXIF data for date/time components
            photoExifDate = photoDateTime[0:4] + "-" + photoDateTime[5:7] + "-" + photoDateTime[8:10]
            photoExifTime = photoDateTime[11:13] + ":" + photoDateTime[14:16]
        except:
            photoExifDate = "Date unknown"
            photoExifTime = "Time unknown"
        
        photoData["fileName"] = fileName                    
        photoData["camera"] = photoCamera
        photoData["lens"] = photoLens
        photoData["shutterSpeed"] = str(photoShutterSpeed)
        photoData["aperture"] = str(photoAperture)
        photoData["iso"] = str(photoISO)
        photoData["focalLength"] = str(photoFocalLength)
        photoData["time"] = photoExifTime
        photoData["date"] = photoExifDate
        photoData["rating"] = "0"
        
        return(photoData)


    def addPhotoToDatabase(self, filter, photoData):
        
        # check that file still exists before proceeding
        if os.path.isfile(photoData["fileName"]):    
            
            # get sightings that match the filter. Should only be a single sighting.
            sightings = self.GetSightings(filter)
            
            if len(sightings) > 0:
                
                s = sightings[0]    
                
                if "photos" not in s.keys():
                    s["photos"] = [photoData]
                
                else:    
                    if photoData not in s["photos"]:
                        s["photos"].append(photoData)
                        
                # add photoData to db lists
                self.addPhotoDataToDb(photoData)
                        
                    
    def writePhotoDataToFile(self, fileName):
        
        # get all sightings with photos
        filter = code_Filter.Filter()
        sightings = self.GetSightingsWithPhotos(filter)
        
        # set up writing CSV to fileName
        with open(fileName, mode='w') as photoDataFile:
            photoDataWriter = csv.writer(photoDataFile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            photoDataWriter.writerow(["ChecklistID", "CommonName", "FileName", "Camera", "Lens", "ShutterSpeed", "Aperture", "ISO", "FocalLength", "Rating"])

            for s in sightings:
                for p in s["photos"]:
                    try:
                        photoDataWriter.writerow([
                                                 s["checklistID"], 
                                                 s["commonName"], 
                                                 p["fileName"],
                                                 p["camera"],
                                                 p["lens"],
                                                 p["shutterSpeed"],
                                                 p["aperture"],
                                                 p["iso"],
                                                 p["focalLength"],
                                                 p["rating"]
                                                 ])
                    except IOError as err:
                        msg = QMessageBox()
                        msg.setIcon(QMessageBox.Warning)
                        msg.setText("Error occurred while saving the photo data to disk.\n" + s["commonName"] + " " + s["checklistID"] + "\n"+  str(err))
                        msg.setWindowTitle("Save Error")
                        msg.setStandardButtons(QMessageBox.Ok)
                        msg.exec_()                        


    def readPhotoDataFromFile(self, fileName):
        
        with open(fileName, mode='r') as photoDataFile:
            csv_reader = csv.DictReader(photoDataFile)
            
            try:
                
                for row in csv_reader:
                
                    photoData = {}
                    filter = code_Filter.Filter()
                    filter.setChecklistID(row["ChecklistID"])
                    filter.setSpeciesName(row["CommonName"])
                    
                    photoData["fileName"] = row["FileName"]
                    photoData["camera"] = row["Camera"]
                    photoData["lens"] = row["Lens"]
                    photoData["shutterSpeed"] = row["ShutterSpeed"]
                    photoData["aperture"] = row["Aperture"]
                    photoData["iso"] = row["ISO"]
                    photoData["focalLength"] = row["FocalLength"]
                    
                    if "Rating" in row.keys():
                        if row["Rating"] in ["0", "1", "2", "3", "4", "5"]:
                            photoData["rating"] = row["Rating"]
                        else:
                            photoData["rating"] = "0"
                    else:
                        photoData["rating"] = "0"
                                        
                    self.addPhotoToDatabase(filter, photoData)    
                    
            except:
                pass
            
        self.photoDataFileOpenFlag = True


    def refreshPhotoLists(self):
        
        self.cameraList = []
        self.lensList = []
        self.shutterSpeedList = []
        self.apertureList = []
        self.focalLengthList=[]
        self.isoList = []
        
        cameraSet = set()
        lensSet = set()
        shutterSpeedSet = set()
        apertureSet= set()
        focalLengthSet = set()
        isoSet = set()
        
        for s in self.sightingList:
            if "photos" in s.keys():
                for p in s["photos"]:
                    if p["camera"] != "":
                        cameraSet.add(p["camera"])
                    if p["lens"] != "":
                        lensSet.add(p["lens"])
                    if p["shutterSpeed"] != "":
                        shutterSpeedSet.add(p["shutterSpeed"])
                    if p["aperture"] != "":
                        apertureSet.add(p["aperture"])
                    if p["iso"] != "":
                        isoSet.add(p["iso"])
                    if p["focalLength"] != "":
                        focalLengthSet.add(p["focalLength"])
                    
        self.cameraList = list(cameraSet)
        self.lensList = list(lensSet)
        self.shutterSpeedList = natsorted(list(shutterSpeedSet), reverse=True)
        self.apertureList = natsorted(list(apertureSet))
        self.isoList = natsorted(list(isoSet))
        self.focalLengthList = natsorted(list(focalLengthSet))
                
                
    def CountSpecies(self, speciesList):
        
        # method to count true species in a list. Entries with parens, /, or sp. or hybrids should not be counted,
        # unless no non-paren entries exist for that species.append
        speciesSet = set()
        
        # use a set (which deletes duplicates) to hold species names
        # remove parens from species names if they exist
        for s in speciesList:
            if "(" in s and " x " not in s:
                speciesSet.add(s.split(" (")[0])
            elif "sp." in s:
                pass
            elif "/" in s:
                pass
            elif " x " in s:
                pass
            else:
                speciesSet.add(s)
        
        # count the species, including species whose parens have been removed
        count = len(speciesSet)
        
        return(count)
        
        
    def ReadCountryStateCodeFile(self, dataFile):
        
        # initialize variable used to store CSV file's data
        countryCodeData = []
        
        # open the country and state code data file
        # and read its lines into a list for future searching
        with open(dataFile, 'r', errors='replace') as csvfile:
            csvdata = csv.reader(csvfile, delimiter=',', quotechar='"')
            for line in csvdata:
                countryCodeData.append(line)
        csvfile.close()
        
        # clear the countryList and stateList because we'll use longer names
        self.countryList = []
        self.stateList = []

        # search through each location in the master location file
        # append the long country and state names when found in the country state code data
        for c in countryCodeData:

#             # append two place holders in the masterLocationList for long country and state names
#             l.append("")
#             l.append("")
#             
            for l in self.masterLocationList:

                # find the long country name by looking for a perfect match of "cc-" for the state code
                # this match is actually for the country because states have characters
                # after the - character
                if l["countryCode"] + "-" == c[1]:

                    # when found, save the long country name to the masterLocationList
                    l["countryName"] = c[2]
                    self.countryList.append(c[2])

                # look for a perfect match for the state code
                if l["stateCode"] == c[1]:
                    
                    # when found, save the long state name to the masterLocationList
                    l["stateName"] = c[2]
                    self.stateList.append(c[2])
                    
                    # no need to keep searching. We've found our long names.
                    break
                    
        # get rid of duplicates in master country and state lists using the set command
        self.countryList = list(set(self.countryList))
        self.stateList = list(set(self.stateList))

        # sort the master country and state lists
        self.countryList.sort()
        self.stateList.sort()

        # self.countryCodeData = countryCodeData
        self.countryStateCodeFileFound = True


    def ReadDataFile(self, DataFile):

        self.ClearDatabase() 
        
        # extract data from zip file if user has chosen a zip file
        #if os.path.splitext(DataFile[0])[1] == ".zip":
        # 
        import zipfile

        if zipfile.is_zipfile(DataFile):  
            
            filehandle = open(DataFile, 'rb')
            
            zfile = zipfile.ZipFile(filehandle)
            
            try:
                csvfile = io.StringIO(zfile.read("MyEBirdData.csv").decode('utf-8'))

            except (KeyError):
                QApplication.restoreOverrideCursor()
                self.eBirdFileOpenFlag = False
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Warning)
                msg.setText("The file failed to load.\n\nPlease check that it is a valid eBird data file.\n")
                msg.setWindowTitle("File failed to load")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()   
                return 
        
        # use csv reader to process csv file if user has selected a csv file
         
        if os.path.splitext(DataFile)[1] == ".csv":        
            csvfile = open(DataFile, 'r') 
        
        # process CSV values from csvfile.        
        csvdata = csv.DictReader(csvfile)  
            
        # initialize temporary list variable to hold location data 
        thisMasterLocationEntry = []
        
        for line in csvdata:
              
            # convert date format from mm-dd-yyyy to yyyy-mm-dd for international standard and sorting ability
            # THIS IS NO LONGER NECESSARY, AS IN MARCH 2019 EBIRD CHANGED THE DATA FORMAT TO THE ONE WE PREFER
            # line[10] = line[10][6:] + "-" + line[10][0:2] + "-" + line[10][3:5]
            
            # append state name in parentheses to county name to differentiate between
            # counties that have the same name but are in different states
            if line["County"] != "":
                line["County"] = line["County"] + " (" + line["State/Province"] + ")" 
                           
            # add blank elements to list so we can later add family and order names if taxonomic file exists
            # also add blank line for subspecies name
            
            # store full name (maybe a subspecies) in sighting
            subspeciesName = deepcopy(line["Common Name"])
            line["Subspecies"] = subspeciesName
            
            # remove any subspecies data in parentheses in species name
            # but keep "(hybrid)" if it's in the name
            if "(" in line["Common Name"]:
                if "hybrid" not in line["Common Name"]:
                    line["Common Name"] = line["Common Name"][:line["Common Name"].index("(") - 1]    
             
            # convert 12-hour time format to 24-hour format for easier sorting and display
            time = line["Time"]
            if "AM" in time:
                time = line["Time"][0:5]
            if "PM" in time:
                time = line["Time"][0:5]
                hour = int(line["Time"][0:2])
                hour = str(hour + 12)
                if hour == "24":
                    hour = "12"
                time = hour + line["Time"][2:5]  
            line["Time"] = time
            
            # add sighting to the main database for use by later searches etc.
            # this sightingList will be used in nearly every search performed by user
            
            # convert line's CSV data into our own dictionary to remove spaces, abbreviations, etc.
            thisSightingDict = defaultdict(
                checklistID=line["Submission ID"],
                commonName=line["Common Name"],
                scientificName=line["Scientific Name"],
                subspeciesName=line["Subspecies"],
                taxonomicOrder=line["Taxonomic Order"],
                count=line["Count"],
                country=line["State/Province"][0:2],
                state=line["State/Province"],
                county=line["County"],
                location=line["Location"],
                latitude=line["Latitude"],
                longitude=line["Longitude"],
                date=line["Date"],
                time=line["Time"],
                protocol=line["Protocol"],
                duration=line["Duration (Min)"],
                allObsReported=line["All Obs Reported"],
                distance=line["Distance Traveled (km)"],
                areaCovered=line["Area Covered (ha)"],
                observers=line["Number of Observers"],
                breedingCode=line["Breeding Code"],
                checklistComments=line["Checklist Comments"],
                regionCodes=[]
                )
            
            if thisSightingDict["areaCovered"] is None:
                thisSightingDict["areaCovered"] = ""
            if thisSightingDict["distance"] is None:
                thisSightingDict["distance"] = ""
            if thisSightingDict["observers"] is None:
                thisSightingDict["observers"] = ""            
            if thisSightingDict["breedingCode"] is None:
                thisSightingDict["breedingCode"] = ""
            if "Observation Details" in line.keys():
                thisSightingDict["speciesComments"]=line["Observation Details"]
            if "Species Comments" in line.keys():
                thisSightingDict["speciesComments"]=line["Species Comments"]
            if thisSightingDict["speciesComments"] is None:
                thisSightingDict["speciesComments"] = ""
            if thisSightingDict["checklistComments"] is None:
                thisSightingDict["checklistComments"] = ""    
            thisSightingDict["family"] = ""
            thisSightingDict["order"] = "" 
                            
            # If a US sighting, use countyCodeDict to assign the unique 5-digit FIPS code for the county
            # we'll use this for choropleths
            if thisSightingDict["country"] == "US" and thisSightingDict["state"] not in ["US-HI", "US-AK"]:
                countyNameWithoutParentheses = thisSightingDict["county"].split(" (")[0]
                if countyNameWithoutParentheses != "":
                    for c in self.countyCodeDict[countyNameWithoutParentheses]:
                        if c[1] == thisSightingDict["state"][3:5]:
                            thisSightingDict["countyCode"] = c[0]
                
                                         
            # add abbreviations for the regions recognized by eBird
            
            # ----------------------------------------            
            # add ABA if in US, Canada, or St. Pierre et Miquelon, but exclude Hawaii
            if thisSightingDict["country"] in ["US", "CA", "PM"]:
                if thisSightingDict["state"] != "US-HI":
                    thisSightingDict["regionCodes"].append("ABA")
            
            # ----------------------------------------            
            # add AOU if if in US, Canada, St. Pierre et Miquelon, Mexico, Central America
            if thisSightingDict["country"] in [
                "US", "CA", "PM", "MX", "GT", "SV", "HN", "CR", "PA",
                "CU", "HT", "DO", "JM", "KY", "PR", "VG", "VI", "AI",
                "MF", "BL", "BQ", "KN", "AG", "MS", "GP", "DM", "BS",
                "BB", "GD", "LC", "VC", "BM", "CP", "NI"
                ]:
                thisSightingDict["regionCodes"].append("AOU")
            
            if thisSightingDict["state"] in [
                "CO-SAP", "UM-67", "UM-71"
                ]:
                thisSightingDict["regionCodes"].append("AOU")

            # ----------------------------------------        
            # add USL if if in Lower 48 US states listing region as designated by eBird
                        
            if thisSightingDict["country"] == "US":
                if thisSightingDict["state"] not in ["US-AK", "US-HI"]:
                    thisSightingDict["regionCodes"].append("USL")

            
            #--------------------------------------- 
            # add AFR if if in Africa
            if thisSightingDict["country"] in [
                "DZ", "AO", "SH", "BJ", "BW", "BF", "BI", "CM", "CV", "CF", "TD", 
                "KM", "CG", "CD", "DJ", "GQ", "ER", "SZ", "ET", "GA", "GM", 
                "GH", "GN", "GW", "CI", "KE", "LS", "LR", "LY", "MG", "MW", "ML", 
                "MR", "MU", "YT", "MA", "MZ", "NA", "NE", "NG", "ST", "RE", "RW", 
                "ST", "SN", "SC", "SL", "SO", "ZA", "SS", "SH", "SD", "SZ", "TZ", 
                "TG", "TN", "UG", "CD", "ZM", "TZ", "ZW"
                ]:
                thisSightingDict["regionCodes"].append("AFR")
            
            if thisSightingDict["state"] == "ES-CN":
                thisSightingDict["regionCodes"].append("AFR")
                
            if thisSightingDict["country"] == "EG":
                if thisSightingDict["state"] not in ["EG-PTS", "EG-JS", "EG-SIN"]:
                    thisSightingDict["regionCodes"].append("AFR")

            # ----------------------------------------        
            # add ASI if if in Asia
            if thisSightingDict["country"] in [        
                "AF", "AM", "AZ", "BH", "BD", "BT", "BN", "KH", "CN", "CX", "CC", 
                "IO", "GE", "HK", "IN", "IR", "IQ", "IL", "JP", "JO", 
                "KW", "KG", "LA", "LB", "MO", "MY", "MV", "MN", "MM", "NP", "KP", 
                "OM", "PK", "PS", "PH", "QA", "SA", "SG", "KR", "LK", "SY", "TW", 
                "TJ", "TH", "TM", "AE", "UZ", "VN", "YE", "SD", "SZ", "TZ", 
                "TG", "TN", "UG", "CD", "ZM", "TZ", "ZW"
                ]:
                thisSightingDict["regionCodes"].append("ASI")
            
            if thisSightingDict["country"] == "TR":
                if thisSightingDict["state"] not in ["TR-22", "TR-39", "TR-59"]:
                    thisSightingDict["regionCodes"].append("ASI")

            if thisSightingDict["country"] == "KZ":
                if thisSightingDict["state"] not in ["KZ-ATY", "KZ-ZAP"]:
                    thisSightingDict["regionCodes"].append("ASI")

            if thisSightingDict["country"] == "ID":
                if thisSightingDict["state"] != "ID-IJ":
                    thisSightingDict["regionCodes"].append("ASI")
                                    
            if thisSightingDict["country"] == "EG":
                if thisSightingDict["state"] in ["EG-PTS", "EG-JS", "EG-SIN"]:
                    thisSightingDict["regionCodes"].append("ASI")
                    
            if thisSightingDict["country"] == "RU":
                if thisSightingDict["state"] in [
                    "RU-YAN", "RU-KHM", "RU-TYU", "RU-OMS", "RU-TOM", "RU-NVS",
                    "RU-ALT", "RU-KEM", "RU-AL", "RU-KK", "RU-KYA", "RU-TY",
                    "RU-IRK", "RU-SA", "RU-BU", "RU-ZAB", "RU-AMU", "RU-KHA",
                    "RU-YEV", "RU-PRI", "RU-MAG", "RU-CHU", "RU-KAM", "RU-SAK"
                    ]:
                    thisSightingDict["regionCodes"].append("ASI")                    

            # ----------------------------------------        
            # add ATL if if in Atlantic listing region
            
            # Note that pelagic sightings more than 200 miles from a state
            # will not be counted here because I don't know how to calculate
            # if a log/lat sighting is 200 miles from a state
            
            if thisSightingDict["country"] in [        
                "BM", "FK", "SH"
                ]:
                thisSightingDict["regionCodes"].append("ATL")


            # ----------------------------------------        
            # add AUE if if in Australasia (eBird) listing region
                        
            if thisSightingDict["country"] in [        
                "AU", "AC", "NF", "NZ", "SB", "VU", "NC", "PG", 
                ]:
                thisSightingDict["regionCodes"].append("AUE")

            if thisSightingDict["state"] in [        
                "ID-IJ", "ID-MA" 
                ]:
                thisSightingDict["regionCodes"].append("AUE")


            # ----------------------------------------        
            # add AUA if if in Australasia (ABA) listing region
                        
            if thisSightingDict["country"] in [        
                "AU", "ID" 
                ]:
                thisSightingDict["regionCodes"].append("AUA")
                

            # ----------------------------------------        
            # add AUS if if in Australia listing region as designated by eBird
                        
            if thisSightingDict["country"] in [        
                "AU", "HM", "CX", "CC", "NF", "AC"
                ]:
                thisSightingDict["regionCodes"].append("AUS")


            # ----------------------------------------        
            # add EUR if if in Europe listing region as designated by eBird
                        
            if thisSightingDict["country"] in [        
                "AL", "AD", "AT", "BY", "BE", "BA", "BG", "HR", "CY", "CZ", "DK", 
                "EE", "FO", "FI", "FR", "DE", "GI", "GR", "HU", "IS", "IE", "IM", 
                "IT", "RS", "LV", "LI", "LT", "LU", "MK", "MT", "MD", "MC", "ME", 
                "NL", "NO", "PL", "PT", "RO", "RU", "SM", "RS", "SK", "SI", 
                "SE", "CH", "UA", "GB", "VA", "JE"
                ]:
                thisSightingDict["regionCodes"].append("EUR")  
                
            # include Spain, but not Canaries
            if thisSightingDict["country"] == "ES":
                if thisSightingDict["state"] != "ES-CN":
                    thisSightingDict["regionCodes"].append("EUR") 
                
            # include Russia, but exclude Asian regions of Russia
            if thisSightingDict["country"] == "RU":
                if thisSightingDict["state"] not in [
                    "RU-YAN", "RU-KHM", "RU-TYU", "RU-OMS", "RU-TOM", "RU-NVS",
                    "RU-ALT", "RU-KEM", "RU-AL", "RU-KK", "RU-KYA", "RU-TY",
                    "RU-IRK", "RU-SA", "RU-BU", "RU-ZAB", "RU-AMU", "RU-KHA",
                    "RU-YEV", "RU-PRI", "RU-MAG", "RU-CHU", "RU-KAM", "RU-SAK"
                    ]:             
                        thisSightingDict["regionCodes"].append("EUR")  

            # include European areas of Turkey
            if thisSightingDict["state"] in ["TR-22", "TR-39", "TR-59"]:
                thisSightingDict["regionCodes"].append("EUR")

            # include European areas of Kazakhstan
            if thisSightingDict["state"] in ["KZ-ATY", "KZ-ZAP"]:
                thisSightingDict["regionCodes"].append("EUR")
                
                
            # ----------------------------------------        
            # add NAM if if in North America listing region as designated by eBird
                        
            if thisSightingDict["country"] in [
                "CA", "PM", "MX", "GT", "SV", "HN", "CR", "PA",
                "CU", "HT", "DO", "JM", "KY", "PR", "VG", "VI", "AI",
                "MF", "BL", "BQ", "KN", "AG", "MS", "GP", "DM", "BS",
                "BB", "GD", "LC", "VC", "BM", "CP", "GL", "NI"
                ]:
                thisSightingDict["regionCodes"].append("NAM") 
                
            if thisSightingDict["state"] in [
                "CO-SAP"
                ]:
                thisSightingDict["regionCodes"].append("NAM")

            if thisSightingDict["country"] == "US":
                if thisSightingDict["state"] != "US-HI":
                    thisSightingDict["regionCodes"].append("NAM")                

   
            # ----------------------------------------        
            # add SAM if if in South America listing region as designated by eBird
                        
            if thisSightingDict["country"] in [
                "AR", "BO", "BR", "CL", "CO", "FK", "GF", 
                "GY", "GY", "PY", "PE", "SR", "UY", "VE", "TT", "CW", "AW"
                ]:
                thisSightingDict["regionCodes"].append("SAM") 
                
            if thisSightingDict["state"] in [
                "BQ-BO"
                ]:
                thisSightingDict["regionCodes"].append("SAM")
            
            if thisSightingDict["country"] == "EC" and thisSightingDict["state"] != "EC-W":
                thisSightingDict["regionCodes"].append("SAM")
                

            # ----------------------------------------        
            # add WIN if if in West Indies listing region as designated by eBird
                        
            if thisSightingDict["country"] in [
                "AI", "AG", "AW", "BS", "BB", "VG", "KY", "VI"
                "CU", "DM", "DO", "GD", "GP", "HT", "JM", "MQ", 
                "MS", "AN", "PR", "KN", "LC", "VC", "TT", "TC" 
                ]:
                thisSightingDict["regionCodes"].append("WIN") 
            
            if thisSightingDict["state"] == "CO-SAP":
                thisSightingDict["regionCodes"].append("WIN")


            # ----------------------------------------        
            # add CAM if if in Central America listing region as designated by eBird
                        
            if thisSightingDict["country"] in [
                "BZ", "CR", "SV", "GT", "HN", "NI", "PA"
                ]:
                thisSightingDict["regionCodes"].append("CAM")

                
            # ----------------------------------------        
            # add SPO if if in South Polar listing region as designated by eBird
                        
            if thisSightingDict["country"] in [
                "AQ", "BV", "GS", "HM"
                ]:
                thisSightingDict["regionCodes"].append("SPO") 
 
                
            # ----------------------------------------        
            # add WH if if in Western Hemisphere listing region as designated by eBird
                        
            if "NAM" in thisSightingDict["regionCodes"]:
                thisSightingDict["regionCodes"].append("WHE")                 

            if "SAM" in thisSightingDict["regionCodes"]:
                thisSightingDict["regionCodes"].append("WHE")
                
            if thisSightingDict["country"] in [
                "CP", "BM", "FK"
                ]:
                thisSightingDict["regionCodes"].append("WHE")                 
                
            if thisSightingDict["state"] in [
                "US-HI", "UM-67", "UM-71", "EC-W"  
                ]:
                thisSightingDict["regionCodes"].append("WHE") 
                
            
            # ------------------------------------------------------    
            # add EH if in Eastern Hemisphere  (not Western, and not South Polar)
            
            if "WHE" not in thisSightingDict["regionCodes"] and "SPO" not in thisSightingDict["regionCodes"]:
                thisSightingDict["regionCodes"].append("EHE")  
                
                                
            # add sighting to checklistDict, even if it's a sp or / species
            # use checklistID as the key
            checklistID = thisSightingDict["checklistID"]
            if checklistID not in self.checklistDict.keys():
                self.checklistDict[checklistID] = [thisSightingDict]
            else:
                self.checklistDict[checklistID].append(thisSightingDict)  

            # add sighting to other dicts only if it's a full species, not a / or sp.
            commonName = thisSightingDict["commonName"]

            #if ("/" not in commonName) and ("sp." not in commonName):
                
            self.allSpeciesList.append(commonName)

            # use species common name as key
            if commonName not in self.speciesDict.keys():
                self.speciesDict[commonName] = [thisSightingDict]
            else:
                self.speciesDict[commonName].append(thisSightingDict)

            # also add subspecies as key to speciesDict
            # to facilitate lookup
            subspeciesName = thisSightingDict["subspeciesName"]
            if subspeciesName not in self.speciesDict.keys():
                self.speciesDict[subspeciesName] = [thisSightingDict]
            else:
                self.speciesDict[subspeciesName].append(thisSightingDict)

            # add sighting to yearDict
            # use 4-digit year as the key
            year = thisSightingDict["date"][0:4]
            if year not in self.yearDict.keys():
                self.yearDict[year] = [thisSightingDict]
            else:
                self.yearDict[year].append(thisSightingDict)

            # add sighting to monthDict
            # use 2-digit month as the key
            month = thisSightingDict["date"][5:7]
            if month not in self.monthDict.keys():
                self.monthDict[month] = [thisSightingDict]
            else:
                self.monthDict[month].append(thisSightingDict)

            # add sighting to dateDict
            # use full date (yyyy-mm-dd) as the key
            date = thisSightingDict["date"]
            if date not in self.dateDict.keys():
                self.dateDict[date] = [thisSightingDict]
            else:
                self.dateDict[date].append(thisSightingDict)

            # add sighting to regionDict
            # use 3-character code as key
            regionCodes = thisSightingDict["regionCodes"]
            for r in regionCodes:
                if r not in self.regionDict.keys():
                    self.regionDict[r] = [thisSightingDict]
                else:
                    self.regionDict[r].append(thisSightingDict)

            # add sighting to countryDict
            # use 2-character code as key
            countryCode = thisSightingDict["country"]
            if countryCode not in self.countryDict.keys():
                self.countryDict[countryCode] = [thisSightingDict]
            else:
                self.countryDict[countryCode].append(thisSightingDict)

            # add sighting to stateDict
            # use cc-ss code as the key
            stateCode = thisSightingDict["state"]
            if stateCode not in self.stateDict.keys():
                self.stateDict[stateCode] = [thisSightingDict]
            else:
                self.stateDict[stateCode].append(thisSightingDict)

            # add sighting to countyDict
            # use county name as key
            # don't add sightings whose county name is absent
            county = thisSightingDict["county"]
            if county != "":
                if county not in self.countyDict.keys():
                    self.countyDict[county] = [thisSightingDict]
                else:
                    self.countyDict[county].append(thisSightingDict)

            # add sighting to locationDict
            # use location name as key
            location = thisSightingDict["location"]
            if location not in self.locationDict.keys():
                self.locationDict[location] = [thisSightingDict]
            else:
                self.locationDict[location].append(thisSightingDict)
            
            # get just the location data from this particular sighting
            # thisMasterLocationEntry = [country, state, county, location]
            thisMasterLocationEntry = defaultdict()
            thisMasterLocationEntry["regionCodes"] = regionCodes
            thisMasterLocationEntry["countryCode"] = countryCode
            thisMasterLocationEntry["stateCode"] = stateCode
            thisMasterLocationEntry["county"] = county
            thisMasterLocationEntry["location"] = location
            
            
            # if this location isn't already in the list, add it
            # we use this list later for populating the filter list of countries, states, counties, locations
            if thisMasterLocationEntry not in self.masterLocationList:
                self.masterLocationList.append(thisMasterLocationEntry)
                for r in regionCodes:
                    self.regionList.append(self.GetRegionName(r))
                self.countryList.append(countryCode)
                self.stateList.append(stateCode)
                if county != "":
                    self.countyList.append(county)
                self.locationList.append(location)
                
            self.sightingList.append(thisSightingDict)
        
        csvfile.close()
        
        # use set function to remove duplicates and then return to a list
        self.allSpeciesList = list(set(self.allSpeciesList))
        self.regionList = list(set(self.regionList))
        self.countryList = list(set(self.countryList))
        self.stateList = list(set(self.stateList))
        self.locationList = list(set(self.locationList))

        # sort 'em 
        self.regionList.sort()
        self.locationList.sort()
        self.countryList.sort()
        self.stateList.sort()
        # self.masterLocationList.sort()
        
        # remove parenthetical state names from counties, unless needed to 
        # differentiate counties with same name in different states
        countyNamesWithoutParens = []
        countyKeyChanges = []
        for cdk in self.countyDict.keys():
            countyNamesWithoutParens.append(cdk.split(" (")[0])
        
        for cdk in self.countyDict.keys():
            if countyNamesWithoutParens.count((cdk.split(" (")[0])) == 1:
                for s in self.countyDict[cdk]:
                    s["county"] = cdk.split(" (")[0]
                countyKeyChanges.append([cdk, cdk.split(" (")[0]])
        
        for ckc in countyKeyChanges:
            self.countyDict[str(ckc[1])] = self.countyDict.pop(str(ckc[0]))
            for ml in self.masterLocationList:
                if ml["county"] == str(ckc[0]):
                    ml["county"] = str(ckc[1])
            
        self.countyList = list(self.countyDict.keys())
        self.countyList.sort()
        
        # set flat indicating that a data file is now open
        self.eBirdFileOpenFlag = True


    def ReadTaxonomyDataFile(self, taxonomyDataFile):
        
        # initialize variable to hold the csv data from the taxonomy file
        taxonomyData = []
        # open the CSV taxonomy file, using "replace" for any problematic characters
        with open(taxonomyDataFile, "r", errors='replace') as csvfile:
            csvdata = csv.reader(csvfile, delimiter=',', quotechar='"')
            # store the csv data in a list for easier searching later on
            for row in csvdata:
                taxonomyData.append(row)

        # initialize thisSciName variable
        thisSciName = ""

        # loop through sighting list to get each species, compare it, and add order and family
        for s in self.sightingList:

            # if this species already has a order/family found, no need to search database again.
            # But if species does not have order/family found, we need to  search the database
            if thisSciName != s["scientificName"]:
                                
                for line in taxonomyData:

                    # if species matches, save the order and family names for the next time we find the species
                    # species will be found in the sighting file in taxonomic order, so each species will be chunked together
                    if s["scientificName"] == line[4]:  # sci names match    
                                                
                        thisSciName = line[4]
                        thisOrder = line[5]
                        thisFamily = line[6]
                        thisQuickEntryCode = line[2]
   
                        if thisFamily not in self.familyList:
                            self.familyList.append(thisFamily)                        

                        if thisOrder not in self.orderList:
                            self.orderList.append(thisOrder)  
                            
                        if [thisFamily, thisOrder] not in self.masterFamilyOrderList:
                            self.masterFamilyOrderList.append([thisFamily, thisOrder])

                        # add species to orderSpeciesDict:
                        if thisOrder not in self.orderSpeciesDict.keys():
                            self.orderSpeciesDict[thisOrder] = [s["commonName"]]
                        else:
                            self.orderSpeciesDict[thisOrder].append(s["commonName"]) 
                            
                        # add species to familySpeciesDict:
                        if thisFamily not in self.familySpeciesDict.keys():
                            self.familySpeciesDict[thisFamily] = [s["commonName"]]
                        else:
                            self.familySpeciesDict[thisFamily].append(s["commonName"]) 
                        
                        # already found info, no need to continue for this species
                        break
                        
            # append the order and family names to the sighting            
            s["order"] = thisOrder
            s["family"] = thisFamily 
            s["quickEntryCode"] = thisQuickEntryCode

        csvfile.close()


    def ReadBBLCodeFile(self, bblFile):

        # initialize variable to hold the csv data from the BBL Code file
        # open the CSV taxonomy file, using "replace" for any problematic characters
        with open(bblFile, "r", errors='replace') as csvfile:
            csvdata = csv.reader(csvfile, delimiter=',', quotechar='"')
            # store the BBL code in a dictionary, using the sci name as the key
            for row in csvdata:
                self.bblCodeDict[str(row[2]).strip()] = row[0].strip()                    
        
                
    def GetFamilies(self, filter, filteredSightingList=[]):
        familiesList = []
        
        # set filteredSightingList to master list if no filteredSightingList specified
        if filteredSightingList == []:
            filteredSightingList = self.GetMinimalFilteredSightingsList(filter)
        
        # for each sighting, test date if necessary. Append new dates to return list.
        # don't consider spuh or slash species
        for s in filteredSightingList:
            if "sp." not in s["commonName"] and "/" not in s["commonName"] and " x " not in s["commonName"]:
                if self.TestSighting(s, filter) is True:
                    if s["family"] not in familiesList:
                        familiesList.append(s["family"])
        
        return(familiesList)

    def GetSightings(self, filter):
        returnList = []
        
        filteredSightingList = self.GetMinimalFilteredSightingsList(filter)          

        for s in filteredSightingList:
            # this is not a single checklist, so remove spuh and slash sightings
            if filter.getChecklistID() == "":
                commonName = s["commonName"]
                # if "/" not in commonName and "sp." not in commonName:
                if self.TestSighting(s, filter) is True:
                    returnList.append(s)
            else:
                # this is a single checklist, so allow spuh and slash sightings
                if self.TestSighting(s, filter) is True:
                    returnList.append(s)        
        
        return(returnList)


    def GetSpeciesWithPhotos(self, filter):
        returnSet = set()
        
        filteredSightingList = self.GetMinimalFilteredSightingsList(filter)

        for s in filteredSightingList:
            commonName = s["commonName"]
            if "/" not in commonName and "sp." not in commonName:
                if self.TestSighting(s, filter) is True:
                    if "photos" in s.keys():
                        returnSet.add(s["commonName"])      
        
        return(returnSet)


    def GetSpeciesWithoutPhotos(self, filter):
        
        unphotographedSpeciesSet = set()

        photographedSpeciesSet = self.GetSpeciesWithPhotos(filter)

        for species in self.allSpeciesList:
            if species not in photographedSpeciesSet:
                unphotographedSpeciesSet.add(species)        
        
        return(unphotographedSpeciesSet)
    

    def GetSightingsWithPhotos(self, filter):
        returnList = []
        photosFound = []
        
        filteredSightingList = self.GetMinimalFilteredSightingsList(filter)

        for s in filteredSightingList:
            commonName = s["commonName"]
            # if "/" not in commonName and "sp." not in commonName:
            if self.TestSighting(s, filter) is True:
                if "photos" in s.keys():
                    if s["photos"][0]["fileName"] not in photosFound:
                        photosFound.append(s["photos"][0]["fileName"])
                        returnList.append(s)
        
        returnList = sorted(returnList, key=lambda x: (float(x["taxonomicOrder"]), x["date"], x["time"]))

        return(returnList)


    def GetPhotos(self, filter):
        returnList = []
        
        filteredSightingList = self.GetMinimalFilteredSightingsList(filter)

        for s in filteredSightingList:
            if "photos" in s.keys():
                for p in s["photos"]:
                    if p["fileName"] not in returnList:
                        returnList.append(p["fileName"])
        
        returnList.sort()
        
        return(returnList)


    def GetSpecies(self, filter, filteredSightingList=[]):
        speciesList = []
        
        # set filteredSightingList to master list if no filteredSightingList specified
        if filteredSightingList == []:
            filteredSightingList = self.GetMinimalFilteredSightingsList(filter)

        # for each sighting, test filter. Append filtered species to return list.
        for s in filteredSightingList:
            if self.TestSighting(s, filter) is True:
                if s["commonName"] not in speciesList:
                    speciesList.append(s["commonName"])
        
        return(speciesList)


    def GetMinimalFilteredSightingsList(self, filter):

        returnList = []
        speciesName = filter.getSpeciesName()
        speciesList = filter.getSpeciesList()
        startDate = filter.getStartDate()
        endDate = filter.getEndDate()
        locationType = filter.getLocationType()
        locationName = filter.getLocationName()
        checklistID = filter.getChecklistID()
        
        # if we're dealing with a sp. or slash species,
        # we need to return the whole database since those sightings
        # aren't in dictionaries
        if "sp." in speciesName or "/" in speciesName:
            return(self.sightingList)
        
        # use narrowest subset possible, according to filter            
        if checklistID != "":
            returnList = self.checklistDict[checklistID]
        elif speciesName != "" and speciesName in self.speciesDict.keys():
            returnList = self.speciesDict[speciesName]
        elif speciesList != []:
            for sp in speciesList:
                for s in self.speciesDict[sp]:
                    returnList. append(s)
        elif startDate != "" and startDate == endDate:
            if startDate in self.dateDict.keys():
                returnList = self.dateDict[startDate]
            else:
                returnList = []
        elif locationType == "Country":
            returnList = self.countryDict[locationName]
        elif locationType == "State":
            returnList = self.stateDict[locationName]
        elif locationType == "County":
            returnList = self.countyDict[locationName]
        elif locationType == "Location" and locationName in self.locationDict.keys():
            returnList = self.locationDict[locationName]                
        else:
            returnList = self.sightingList  
        
        return(returnList)

    def GetSpeciesWithData(self, filter, filteredSightingList=[], includeSpecies="Species"):
        filteredDictWithDates = {}
        checklistIDs = {}
        returnList = []
        allChecklists = set()
        
        # if no filteredSightingList is specified, create one.
        # use narrowest subset possible, according to filter            
        if filteredSightingList == []:

            filteredSightingList = self.GetMinimalFilteredSightingsList(filter)
            
        # loop through sightingList and check each sighting for the filtered list criteria
        for sighting in filteredSightingList:
            
            if self.TestSighting(sighting, filter) is True:
                
                # store the sighting date so we can get first and last later
                # include the taxonomy entry so we can sort the list by taxonomy later
                # include the main species name so we can store it in SpeciesList hidden data
                # include the checklist number so we can count checklists for each species
                thisDateTaxSpecies = [sighting["date"], sighting["taxonomicOrder"], sighting["commonName"], sighting["checklistID"], sighting["count"]]
                
                # decide whether we're returning only species or also subspecies
                if includeSpecies == "Species":
                    key = sighting["commonName"]
                if includeSpecies == "Subspecies":
                    key = sighting["subspeciesName"]
                
                # add the date and taxonomy number to a temp dictionary 
                # we'll use this dictionary later to find the first and last dates
                if key not in filteredDictWithDates.keys():
                    filteredDictWithDates[key] = [thisDateTaxSpecies]
                else:
                    filteredDictWithDates[key].append(thisDateTaxSpecies)
                    
                # add the checklist ID to a temp dictionary 
                # we'll use this dictionary later to sum the checklists per species
                if key not in checklistIDs.keys():
                    checklistIDs[key] = [thisDateTaxSpecies[3]]
                else:
                    checklistIDs[key].append(thisDateTaxSpecies[3])       
       
                # add checklistID to allChecklist set so we can count all the checklists later
                allChecklists.add(sighting["checklistID"])
    
        # get the total number of checklists so we can compute percentages 
        # of checklists for each species
        allChecklistCount = len(allChecklists)
        
        if len(filteredDictWithDates) > 0:            
            
            # initiate currentSpeciesIndex with data from first element in filteredListWithDates
            for s in filteredDictWithDates.keys():
                tempSpeciesList = filteredDictWithDates[s]
                tempSpeciesList.sort()
                thisCommonName = s
                thisFirstDate = tempSpeciesList[0][0]
                thisLastDate = tempSpeciesList[len(tempSpeciesList) - 1][0]
                thisTaxNumber = float(tempSpeciesList[0][1])
                thisTopLevelSpeciesName = tempSpeciesList[0][2]
                thisChecklistCount = len(checklistIDs[s])
                percentageOfChecklists = round(100 * thisChecklistCount / allChecklistCount, 2)
                
                # count up the number of individuals seen
                count = 0
                for sighting in tempSpeciesList:
                    if sighting[4] == "X" or count == "X":
                        count = "X"
                    else:
                        count = count + int(sighting[4])
                
                returnList.append([
                    thisCommonName,
                    thisFirstDate,
                    thisLastDate,
                    thisTaxNumber,
                    thisTopLevelSpeciesName,
                    thisChecklistCount,
                    percentageOfChecklists,
                    count
                    ])
                
        returnList = sorted(returnList, key=lambda x: (x[3]))
        
        return(returnList)

    def GetUniqueSpeciesForLocation(self, filter, location, speciesList, filteredSightingList=[],):
        uniqueSpeciesList = []
        
        # set filteredSightingList to master list if no filteredSightingList specified
        if filteredSightingList == []:
            filteredSightingList = self.GetMinimalFilteredSightings(filter)
        
        # for each sighting, test date if necessary. Append new dates to return list.
        for species in speciesList:
            isSeenNowhereElse = True
            for s in filteredSightingList:
                if self.TestSighting(s, filter) is True:
                    if s["commonName"] == species and s["location"] != location:
                        isSeenNowhereElse = False
                        break
                
            if isSeenNowhereElse == True:
                if species not in uniqueSpeciesList:
                    uniqueSpeciesList.append(species)
                    
        return(uniqueSpeciesList)


    def TestIndividualPhoto(self, photoData, filter):
        
        filterCamera = filter.getCamera()
        filterLens = filter.getLens()
        filterStartShutterSpeed = filter.getStartShutterSpeed()
        filterEndShutterSpeed = filter.getEndShutterSpeed()
        filterStartAperture = filter.getStartAperture()
        filterEndAperture = filter.getEndAperture()
        filterStartFocalLength = filter.getStartFocalLength()
        filterEndFocalLength = filter.getEndFocalLength()
        filterStartIso = filter.getStartIso()
        filterEndIso = filter.getEndIso()
        filterStartRating = filter.getStartRating()
        filterEndRating = filter.getEndRating()
        
        # check photo settings
        # note that a sighting can have several attached photos
        # we only reject a sighting here if all attached photos fail
        
        if filterCamera != "":
            if photoData["camera"] != filterCamera:
                return(False)
        
        if filterLens != "":
            if photoData["lens"] != filterLens:
                return(False)

        if filterStartShutterSpeed != "" and filterEndShutterSpeed != "":
            # strip away the 1/ characters at start of shutter speeds
            filterStartShutterSpeed = int(filterStartShutterSpeed[2:])
            filterEndShutterSpeed = int(filterEndShutterSpeed[2:])
            shutterSpeed = photoData["shutterSpeed"]
            if shutterSpeed != "":
                shutterSpeed = int(shutterSpeed[2:])
                if not (shutterSpeed <= filterStartShutterSpeed and shutterSpeed >= filterEndShutterSpeed):
                    return(False)
            else:
                return(False) 
                            
        if filterStartShutterSpeed != "" and filterEndShutterSpeed == "":
            # strip away the 1/ characters at start of shutter speeds
            filterStartShutterSpeed = int(filterStartShutterSpeed[2:])
            shutterSpeed = photoData["shutterSpeed"]
            if shutterSpeed != "":
                shutterSpeed = int(shutterSpeed[2:])
                if shutterSpeed > filterStartShutterSpeed:
                    return(False)
            else:
                return(False) 
            
        if filterStartShutterSpeed == "" and filterEndShutterSpeed != "":
            # strip away the 1/ characters at start of shutter speeds            
            filterEndShutterSpeed = int(filterEndShutterSpeed[2:])
            shutterSpeed = photoData["shutterSpeed"]
            if shutterSpeed != "":
                shutterSpeed = int(shutterSpeed[2:])
                if shutterSpeed < filterEndShutterSpeed:
                    return(False)
            else:
                return(False) 
            
        if filterStartAperture != "" and filterEndAperture != "":
            filterStartAperture = float(filterStartAperture)
            filterEndAperture = float(filterEndAperture)
            aperture = photoData["aperture"]
            if aperture != "":
                aperture = float(aperture)
                if aperture < filterStartAperture or aperture > filterEndAperture:
                    return(False)
            else:
                return(False) 
                            
        if filterStartAperture != "" and filterEndAperture == "":
            filterStartAperture = float(filterStartAperture)
            aperture = photoData["aperture"]
            if aperture != "":
                aperture = float(aperture)
                if aperture < filterStartAperture:
                    return(False)
            else:
                return(False) 
            
        if filterStartAperture == "" and filterEndAperture != "":
            filterEndAperture = float(filterEndAperture)
            aperture = photoData["aperture"]
            if aperture != "":
                aperture = float(aperture)
                if aperture > filterEndAperture:
                    return(False)
            else:
                return(False) 
            
        if filterStartIso != "" and filterEndIso != "":
            filterStartIso = int(filterStartIso)
            filterEndIso = int(filterEndIso)
            iso = photoData["iso"]
            if iso != "":
                iso = int(iso)
                if iso < filterStartIso or iso > filterEndIso:
                    return(False)
            else:
                return(False) 
                            
        if filterStartIso != "" and filterEndIso == "":
            filterStartIso = int(filterStartIso)
            iso = photoData["iso"]
            if iso != "":
                iso = int(iso)
                if iso < filterStartIso:
                    return(False)
            else:
                return(False) 
            
        if filterStartIso == "" and filterEndIso != "":
            filterEndIso = int(filterEndIso)
            iso = photoData["iso"]
            if iso != "":
                iso = int(iso)
                if iso > filterEndIso:
                    return(False)
            else:
                return(False) 
                        
        if filterStartFocalLength != "" and filterEndFocalLength != "":
            filterStartFocalLength = filterStartFocalLength.split(" mm")[0]
            filterStartFocalLength = int(filterStartFocalLength)
            filterEndFocalLength = filterEndFocalLength.split(" mm")[0]
            filterEndFocalLength = int(filterEndFocalLength)
            focalLength = photoData["focalLength"]
            if focalLength != "":
                focalLength = focalLength.split(" mm")[0]
                focalLength = int(focalLength)
                if focalLength < filterStartFocalLength or focalLength > filterEndFocalLength:
                    return(False)
            else:
                return(False) 
                            
        if filterStartFocalLength != "" and filterEndFocalLength == "":
            filterStartFocalLength = filterStartFocalLength.split(" mm")[0]            
            filterStartFocalLength = int(filterStartFocalLength)
            focalLength = photoData["focalLength"]
            if focalLength != "":
                focalLength = focalLength.split(" mm")[0]                
                focalLength = int(focalLength)
                if focalLength < filterStartFocalLength:
                    return(False)
            else:
                return(False) 
            
        if filterStartFocalLength == "" and filterEndFocalLength != "":
            filterEndFocalLength = filterEndFocalLength.split(" mm")[0]            
            filterEndFocalLength = int(filterEndFocalLength)
            focalLength = photoData["focalLength"]
            if focalLength != "":
                focalLength = focalLength.split(" mm")[0]                
                focalLength = int(focalLength)
                if focalLength > filterEndFocalLength:
                    return(False)
            else:
                return(False)                  
            
        if filterStartRating != "" and filterEndRating != "":
            filterStartRating = int(filterStartRating)
            filterEndRating = int(filterEndRating)
            rating = photoData["rating"]
            if rating != "" and rating is not None:
                rating = int(rating)
                if rating < filterStartRating or rating > filterEndRating:
                    return(False)
            else:
                return(False) 
                            
        if filterStartRating != "" and filterEndRating == "":
            filterStartRating = int(filterStartRating)
            rating = photoData["rating"]
            if rating != "":
                rating = int(rating)
                if rating < filterStartRating:
                    return(False)
            else:
                return(False) 
            
        if filterStartRating == "" and filterEndRating != "":
            filterEndRating = int(filterEndRating)
            rating = photoData["rating"]
            if rating != "":
                rating = int(rating)
                if rating > filterEndRating:
                    return(False)
            else:
                return(False)                    
                                         
        # if we've arrived here, the photo passes the filter. 
        return(True)

    
    def TestSighting(self, sighting, filter):
        
        locationType = filter.getLocationType()  # str   choices are Region, Country, County, State, Location, or ""
        locationName = filter.getLocationName()  # str   name of region or location  or ""
        startDate = filter.getStartDate()  # str   format yyyy-mm-dd  or ""
        endDate = filter.getEndDate()  # str   format yyyy-mm-dd  or ""
        startSeasonalMonth = filter.getStartSeasonalMonth()  # str   format mm
        startSeasonalDay = filter.getStartSeasonalDay()  # str   format dd
        endSeasonalMonth = filter.getEndSeasonalMonth()  # str   format  dd
        endSeasonalDay = filter.getEndSeasonalDay()  # str   format dd
        checklistID = filter.getChecklistID()  # str   checklistID
        sightingDate = sighting["date"]  # str   format yyyy-mm-dd
        speciesName = filter.getSpeciesName()  # str   species Name
        speciesList = filter.getSpeciesList()  # list  of species names
        scientificName = filter.getScientificName() #str    scientific name
        order = filter.getOrder()  # str   order name
        family = filter.getFamily()  # str   family name
        time = filter.getTime()  # str   format HH:DD in 24-hour format
        commonNameSearch = filter.getCommonNameSearch()

        sightingHasPhoto = filter.getSightingHasPhoto()
        speciesHasPhoto = filter.getSpeciesHasPhoto()
        validPhotoSpecies = filter.getValidPhotoSpecies()
        camera = filter.getCamera()
        lens = filter.getLens()
        startShutterSpeed = filter.getStartShutterSpeed()
        endShutterSpeed = filter.getEndShutterSpeed()
        startAperture = filter.getStartAperture()
        endAperture = filter.getEndAperture()
        startFocalLength = filter.getStartFocalLength()
        endFocalLength = filter.getEndFocalLength()
        startIso = filter.getStartIso()
        endIso = filter.getEndIso()
        startRating = filter.getStartRating()
        endRating = filter.getEndRating()
                
        # Check every filter setting. Return False immediately if sighting fails.
        # If sighting survives the filter, return True

        # if any photo settings have been specified, check whether sighting has photos
        # reject sighting if it doesn't have a photo
        if (
            sightingHasPhoto == "Has photo" or
            camera != "" or
            lens != "" or
            startShutterSpeed != "" or
            endShutterSpeed != "" or
            startAperture != "" or
            endAperture != "" or           
            startFocalLength != "" or
            endFocalLength != "" or            
            startIso != "" or
            endIso != "" or
            speciesHasPhoto == "Photographed" or  
            startRating != "" or
            endRating != ""       
            ):
            if "photos" not in sighting.keys():
                return(False)
        
        # reject if "no photo" was specified but sighting has photo
        if sightingHasPhoto == "No photo":
            if "photos" in sighting.keys():
                return(False)
        
        # if user selected a value for whether a species has a photo, 
        # check if commonName is in the supplied set.
        # if we're checking for "Photographed," the supplied set contains photographed species
        # if we're checking for "Not pPhotographed," the supplied set contains UNphotographed species     
        if validPhotoSpecies != []:
            if sighting["commonName"] not in validPhotoSpecies:
                return(False)

        # if a commonNameSearch string has been specified, check if sighting matches
        if commonNameSearch != "":
            # check to see if s: prepends the search, in which case we need to search sci name
            if "s:" in commonNameSearch:
                commonNameSearch = commonNameSearch.strip()
                if len(commonNameSearch) > 2:
                    if commonNameSearch[0:2].lower() == "s:":
                        sciNameSearch = commonNameSearch[2:]
                        if sciNameSearch.lower() not in sighting["scientificName"].lower():
                            return(False)
                    else:
                        return(False)
                else:
                    return(False)
                
            else:
                if commonNameSearch.lower() not in sighting["commonName"].lower():
                    if commonNameSearch.lower() not in sighting["subspeciesName"].lower():
                        return(False)
            
        # if a checklistID has been specified, check if sighting matches
        if checklistID != "":
            if checklistID != sighting["checklistID"]:
                return(False)

        # if speciesName has been specified, check it
        if speciesName != "":
            if speciesName != sighting["commonName"] and speciesName != sighting["subspeciesName"]:
                return(False)

        # if scientificName has been specified, check it
        if scientificName != "":
            if scientificName != sighting["scientificName"]:
                return(False)

        # if order  has been specified, check it
        if order != "":
            if order != sighting["order"]:
                return(False)

        # if family  has been specified, check it
        if family != "":
            if family != sighting["family"]:
                return(False)
                
        # if speciesList has been specified, check it
        if speciesList != []:
            if sighting["commonName"] not in speciesList:
                return(False)                    

        # if time has been specified, check it
        # don't try checking if sighting is an historical sighting without a time
        if time != "" and sighting["time"] != "":
            # if time exactly matches sighting start time, it passes the filter test
            # if time doesn't match exactly, check whether time is between start time and end time
            if time != sighting["time"]:
                                
                # now use DateTime functions so we can add duration minutes to find end time efficiently
                # adding duration minutes could take us to a new hour, day, month, or year
                durationMinutes = sighting["duration"]
                if durationMinutes is None or durationMinutes == "":
                    durationMinutes = 0
                else:
                    durationMinutes = int(durationMinutes)
                    
                filterDateTime = datetime.datetime(int(startDate[0:4]), int(startDate[5:7]), int(startDate[8:10]), int(time[0:2]), int(time[3:5]))

                sightingStartDateTime = datetime.datetime(int(sightingDate[0:4]), int(sightingDate[5:7]), int(sightingDate[8:10]), int(sighting["time"][0:2]), int(sighting["time"][3:5]))
                
                sightingTimeDelta = datetime.timedelta(0, 0, 0, 0, durationMinutes)
                sightingEndDateTime = sightingStartDateTime + sightingTimeDelta
                
                if not ((sightingStartDateTime <= filterDateTime) and (filterDateTime <= sightingEndDateTime)):                
                
                    return(False)
                
        # check if location matches for sighting; flag species that fit the location
        # no need to check if locationType is ""
        if not locationType == "":
            if locationType == "Region":
                if not locationName in sighting["regionCodes"]:
                    return(False)
            if locationType == "Country":
                if not locationName == sighting["country"]:
                    return(False)
            if locationType == "State":
                if not locationName == sighting["state"]:
                    return(False)   
            if locationType == "County":
                if not locationName == sighting["county"]:
                    return(False)
            if locationType == "Location":
                if not locationName == sighting["location"]:
                    return(False)                    
        
        # check date for matches for sighting range or seasonal range; disqualify sighting if date doesn't fit specific date range
        if not ((startDate == "") or (endDate == "")):
            # if sightingDate is before start date
            if sightingDate < startDate:
                return(False)
            # if sightingDate is after end date
            if sightingDate > endDate: 
                return(False)
        
        # check for seasonal range using month and date parts; disqualify sighting if date doesn't fit in seasonal range
        if not ((startSeasonalMonth == "") or (endSeasonalMonth == "")):
            sightingMonth = sightingDate[5:7]
            sightingDay = sightingDate[8:]
            # if startSeasonalMonth is earlier than endSeasonalMonth (e.g., July to October)
            if startSeasonalMonth < endSeasonalMonth:
                if sightingMonth < startSeasonalMonth:
                    return(False)
                if sightingMonth > endSeasonalMonth:
                    return(False)
                if sightingMonth == startSeasonalMonth:
                    if sightingDay < startSeasonalDay:
                        return(False)
                if sightingMonth == endSeasonalMonth:
                    if sightingDay > endSeasonalDay:
                        return(False)
            # if endSeasonalMonth is earlier than startSeasonalMonth (e.g., October to February)                                        
            if startSeasonalMonth > endSeasonalMonth:
                if sightingMonth < startSeasonalMonth:
                    if sightingMonth > endSeasonalMonth:
                        return(False)
                if sightingMonth == startSeasonalMonth:
                    if sightingDay < startSeasonalDay:
                        return(False)
                if sightingMonth == endSeasonalMonth:
                    if sightingDay > endSeasonalDay:
                        return(False)
            # if endSeasonalMonth is same as startSeasonalMonth (e.g., October and October)
            if startSeasonalMonth == endSeasonalMonth:
                if startSeasonalDay < endSeasonalDay:
                    if not sightingMonth == startSeasonalMonth:
                        return(False)
                    if sightingDay < startSeasonalDay:
                        return(False)
                    if sightingDay > endSeasonalDay:
                        return(False)
                if startSeasonalDay > endSeasonalDay:
                    if sightingMonth < startSeasonalMonth:
                        if sightingMonth > endSeasonalMonth:
                            return(False)
                    if sightingMonth == startSeasonalMonth:
                        if sightingDay > startSeasonalDay:
                            if sightingDay < endSeasonalDay:
                                return(False)
                if startSeasonalDay == endSeasonalDay:
                    if not sightingDay == startSeasonalDay:
                        return(False)
                    if not sightingMonth == startSeasonalMonth:
                        return(False)
        
        # check photo settings
        # note that a sighting can have several attached photos
        # we only reject a sighting here if all attached photos fail
        # For each sighting, test each photo. If any photo passes filter, the sighting passes filter
        
        if camera != "":
            cameraOK = False
            for p in sighting["photos"]:
                if camera == p["camera"]:
                    cameraOK = True
            if cameraOK is False:
                return(False)
        
        if lens != "":
            lensOK = False
            for p in sighting["photos"]:
                if lens == p["lens"]:
                    lensOK= True
            if lensOK is False:
                return(False)      

        if startShutterSpeed != "" and endShutterSpeed == "":
            shutterSpeedOK = False
            filterStartShutterSpeed = startShutterSpeed[2:]
            filterStartShutterSpeed = float(filterStartShutterSpeed)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                shutterSpeed = p["shutterSpeed"]
                if shutterSpeed != "":
                    shutterSpeed = shutterSpeed[2:]
                    shutterSpeed = float(shutterSpeed)
                    if shutterSpeed <= filterStartShutterSpeed:
                        shutterSpeedOK= True
            if shutterSpeedOK is False:
                return(False)   

        if startShutterSpeed == "" and endShutterSpeed != "":
            shutterSpeedOK = False
            filterEndShutterSpeed = endShutterSpeed[2:]
            filterEndShutterSpeed = float(filterEndShutterSpeed)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                shutterSpeed = p["shutterSpeed"]
                if shutterSpeed != "":
                    shutterSpeed = shutterSpeed[2:]
                    shutterSpeed = float(shutterSpeed)
                    if shutterSpeed >= filterEndShutterSpeed:
                        shutterSpeedOK= True
            if shutterSpeedOK is False:
                return(False)  
                            
        if endShutterSpeed != "" and startShutterSpeed != "":
            shutterSpeedOK= False
            filterStartShutterSpeed = startShutterSpeed[2:]
            filterStartShutterSpeed = float(filterStartShutterSpeed)
            filterEndShutterSpeed = endShutterSpeed[2:]
            filterEndShutterSpeed = float(filterEndShutterSpeed)
            for p in sighting["photos"]:
                # convert the string to an integer
                shutterSpeed = p["shutterSpeed"]
                if shutterSpeed != "":
                    shutterSpeed = shutterSpeed[2:]
                    shutterSpeed = float(shutterSpeed)
                    if shutterSpeed <= filterStartShutterSpeed and shutterSpeed >= filterEndShutterSpeed:
                        shutterSpeedOK = True
            if shutterSpeedOK is False:
                return(False)  
                             
        if startAperture != "" and endAperture == "":
            apertureOK = False
            filterStartAperture = float(startAperture)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                aperture = p["aperture"]
                if aperture != "":
                    aperture = float(aperture)
                    if aperture >= filterStartAperture:
                        apertureOK= True
            if apertureOK is False:
                return(False)   

        if startAperture == "" and endAperture != "":
            apertureOK = False
            filterEndAperture = float(endAperture)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                aperture = p["aperture"]
                if aperture != "":
                    aperture = float(aperture)
                    if aperture >= filterEndAperture:
                        apertureOK= True
            if apertureOK is False:
                return(False)  
                            
        if endAperture != "" and startAperture != "":
            apertureOK= False
            filterStartAperture = float(startAperture)
            filterEndAperture = float(endAperture)
            for p in sighting["photos"]:
                # convert the string to an integer
                aperture = p["aperture"]
                if aperture != "":
                    aperture = float(aperture)
                    if aperture >= filterStartAperture and aperture <= filterEndAperture:
                        apertureOK = True
            if apertureOK is False:
                return(False)  

        if startIso != "" and endIso == "":
            isoOK = False
            filterStartIso = int(startIso)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                iso = p["iso"]
                if iso != "":
                    iso = int(iso)
                    if iso >= filterStartIso:
                        isoOK= True
            if isoOK is False:
                return(False)   

        if startIso == "" and endIso != "":
            isoOK = False
            filterEndIso = int(endIso)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                iso = p["iso"]
                if iso != "":
                    iso = int(iso)
                    if iso <= filterEndIso:
                        isoOK= True
            if isoOK is False:
                return(False)  
                            
        if endIso != "" and startIso != "":
            isoOK= False
            filterStartIso = int(startIso)
            filterEndIso = int(endIso)
            for p in sighting["photos"]:
                # convert the string to an integer
                iso = p["iso"]
                if iso != "":
                    iso = int(iso)
                    if iso >= filterStartIso and iso <= filterEndIso:
                        isoOK = True
            if isoOK is False:
                return(False)  

        if startFocalLength != "" and endFocalLength == "":
            focalLengthOK = False
            filterStartFocalLength = startFocalLength.split(" mm")[0]            
            filterStartFocalLength = int(filterStartFocalLength)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                focalLength = p["focalLength"]
                if focalLength != "":
                    focalLength = focalLength.split(" mm")[0]                    
                    focalLength = int(focalLength)
                    if focalLength >= filterStartFocalLength:
                        focalLengthOK= True
            if focalLengthOK is False:
                return(False)   

        if startFocalLength == "" and endFocalLength != "":
            focalLengthOK = False
            filterEndFocalLength = endFocalLength.split(" mm")[0]            
            filterEndFocalLength = int(filterEndFocalLength)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                focalLength = p["focalLength"]
                if focalLength != "":
                    focalLength = focalLength.split(" mm")[0]                    
                    focalLength = int(focalLength)
                    if focalLength <= filterEndFocalLength:
                        focalLengthOK= True
            if focalLengthOK is False:
                return(False)  
                            
        if endFocalLength != "" and startFocalLength != "":
            focalLengthOK= False
            filterStartFocalLength = startFocalLength.split(" mm")[0]            
            filterStartFocalLength = int(filterStartFocalLength)
            filterEndFocalLength = endFocalLength.split(" mm")[0]            
            filterEndFocalLength = int(filterEndFocalLength)
            for p in sighting["photos"]:
                # convert the string to an integer
                focalLength = p["focalLength"]
                if focalLength != "":
                    focalLength = focalLength.split(" mm")[0]                    
                    focalLength = int(focalLength)
                    if focalLength >= filterStartFocalLength and focalLength <= filterEndFocalLength:
                        focalLengthOK = True
            if focalLengthOK is False:
                return(False)  

        if startRating != "" and endRating == "":
            ratingOK = False
            filterStartRating = int(startRating)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                rating = p["rating"]
                if rating != "":
                    rating = int(rating)
                    if rating >= filterStartRating:
                        ratingOK= True
            if ratingOK is False:
                return(False)   

        if startRating == "" and endRating != "":
            ratingOK = False
            filterEndRating = int(endRating)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                rating = p["rating"]
                if rating != "":
                    rating = int(rating)
                    if rating >= filterEndRating:
                        ratingOK= True
            if ratingOK is False:
                return(False)  
                            
        if endRating != "" and startRating != "":
            ratingOK= False
            filterStartRating = int(startRating)
            filterEndRating = int(endRating)
            for p in sighting["photos"]:
                # convert the string to an integer
                rating = p["rating"]
                if rating != "":
                    rating = int(rating)
                    if rating >= filterStartRating and rating <= filterEndRating:
                        ratingOK = True
            if ratingOK is False:
                return(False) 

        # if we've arrived here, the sighting passes the filter. 
        return(True)


    def GetDates(self, filter, filteredSightingList=[]):
        dateList = set()
        needToCheckFilter = False
                
        # set filteredSightingList to master list if no filteredSightingList specified
        if filteredSightingList == []:
            filteredSightingList = self.GetMinimalFilteredSightingsList(filter)
            needToCheckFilter = True
                
        # for each sighting, test date if necessary. Append new dates to return list.
        for s in filteredSightingList:
            if needToCheckFilter is True:
                if self.TestSighting(s, filter) is True:
                    dateList.add(s["date"])
            else:
                dateList.add(s["date"])
        
        # convert the set to a list and sort it. 
        dateList = list(dateList)
        dateList.sort()
        
        return(dateList)


    def GetStartTimes(self, filter, filteredSightingList=[]):
        timeList = set()
        needToCheckFilter = False
                
        # set filteredSightingList to master list if no filteredSightingList specified
        if filteredSightingList == []:
            filteredSightingList = self.GetMinimalFilteredSightingsList(filter)
            needToCheckFilter = True
                
        # for each sighting, test time if necessary. Append new times to return list.
        for s in filteredSightingList:
            if needToCheckFilter is True:
                if self.TestSighting(s, filter) is True:
                    timeList.add(s["time"])
            else:
                timeList.add(s["time"])
        
        # convert the set to a list and sort it. 
        timeList = list(timeList)
        timeList.sort()
        
        return(timeList)
    
    def ClearDatabase(self):
        
        self.eBirdFileOpenFlag = False
        self.countryStateCodeFileFound = False
        self.allSpeciesList = []
        self.familyList = []
        self.masterLocationList = []
        self.countryList = []
        self.stateList = []
        self.countyList = []
        self.locationList = []
        self.sightingList = []
        self.speciesDict = defaultdict()
        self.yearDict = defaultdict()
        self.monthDict = defaultdict()
        self.dateDict = defaultdict()
        self.regionDict = defaultdict()
        self.countryDict = defaultdict()
        self.stateDict = defaultdict()
        self.countyDict = defaultdict()
        self.locationDict = defaultdict()
        self.checklistDict = defaultdict()

    def ClearPhotoSettings(self):
        
        self.cameraList = []
        self.lensList = []
        self.shutterSpeedList = []
        self.apertureList = []
        self.focalLengthList=[]
        self.isoList = []
        
        # remove photo data from sightings
        for s in self.sightingList:
            if "photos" in s.keys():
                del s["photos"]
                
        self.photoDataFileOpenFlag = False
        

    def GetChecklists(self, filter):
        returnList = []
        checklistIDs = set()
        
        # speed retreaval by choosing minimal set of sightings to search
        minimalSightingList = self.GetMinimalFilteredSightingsList(filter)
                
        # gather the IDs of checklists that match the filter
        for s in minimalSightingList:
            if self.TestSighting(s, filter) is True:
                checklistIDs .add(s["checklistID"])
        
        # get all the sightings that match these checklistIDs
        for c in checklistIDs:
            
            # set up blank list to hold species names
            checklistSpecies = []
            
            # use the checklistDict to return sightings that match checklist ID
            for sighting in self.checklistDict[c]:
                
                # append species common name to list, so we can count the species
                checklistSpecies.append(sighting["commonName"])
                
            # count the species, discarding superfluous subspecies, spuhs and slashes when necessary
            speciesCount = self.CountSpecies(checklistSpecies)
            
            # compile data for checklist (id, state (which includes country prefix), county, location, date, time, speciesCount)
            checklistData = [
                sighting["checklistID"],
                sighting["state"],
                sighting["county"],
                sighting["location"],
                sighting["date"],
                sighting["time"],
                speciesCount,
                sighting["duration"]
                ]
            
            returnList.append(checklistData)    
            
        # sort by country, county, location, date, time
        returnList = sorted(returnList, key=lambda x: (x[1], x[2], x[3], x[4], x[5]))

        return(returnList)

    def GetFindResults(self, searchString, checkedBoxes):
        
        foundSet = set()
        
        for s in self.sightingList:
            for c in checkedBoxes:
                if c == "chkCommonName":
                    if searchString.lower() in s["commonName"].lower():
                        foundSet.add(("Common Name", s["checklistID"], s["location"], s["date"], s["commonName"]))
                if c == "chkScientificName":
                    if searchString.lower() in s["scientificName"].lower():
                        foundSet.add(("Scientific Name", s["checklistID"], s["location"], s["date"], s["scientificName"]))                    
                if c == "chkCountryName":
                    if searchString.lower() in self.GetCountryName(s["country"]).lower():
                        foundSet.add(("Country", s["checklistID"], s["location"], s["date"], self.GetCountryName(s[5][0:2])))
                if c == "chkStateName":
                    if searchString.lower() in self.GetStateName(s["state"]).lower():
                        foundSet.add(("State", s["checklistID"], s["location"], s["date"], self.GetStateName(s["state"])))
                if c == "chkCountyName":
                    if searchString.lower() in s["county"].lower():
                        foundSet.add(("County", s["checklistID"], s["location"], s["date"], s["county"]))
                if c == "chkLocationName":
                    if searchString.lower() in s["location"].lower():
                        foundSet.add(("Location", s["checklistID"], s["location"], s["date"], s["location"]))
                if c == "chkSpeciesComments":
                    if searchString.lower() in s["speciesComments"].lower():
                        foundSet.add(("Species Comments", s["checklistID"], s["location"], s["date"], s["speciesComments"]))
                if c == "chkChecklistComments":                    
                    if searchString.lower() in s["checklistComments"].lower():
                        foundSet.add(("Checklist Comments", s["checklistID"], s["location"], s["date"], s["checklistComments"]))
                
            foundList = list(foundSet)
            foundList.sort()
                
        return(foundList)

    def GetLastDayOfMonth(self, month):
                
        # find last day of the specified month
        if month in ["01", "1", "03", "3", "05", "5", "07", "7", "08", "8", "10", "12"]:
            lastDayOfThisMonth = "31"
        if month in ["04", "4", "06", "6", "09", "9", "11"]:
            lastDayOfThisMonth = "30"
        if month in ["02", "2"]:
            lastDayOfThisMonth = "29"
        return(lastDayOfThisMonth)

    def GetLocationCoordinates(self, location):
        coordinates = []
        s = self.locationDict[location][0]
        coordinates.append(s["latitude"])
        coordinates.append(s["longitude"])

        return(coordinates)

    def GetLocations(self, filter, queryType="OnlyLocations", filteredSightingList=[]):
        # queryType specifies which data fields to return in the returnList
        # "OnlyLocations" returns just the location names
        # "Checklist"returns  locationName, count, checklistID, and time
        # "LocationHierarchy" returns country, county, and location (country includes the state code)
        
        returnList = []
        
        if queryType == "Dates":
            tempDateDict = {}
        
        speciesName = filter.getSpeciesName()
        
        # set filteredSightingList to master list if no filteredSightingList specified
        if filteredSightingList == []:
            filteredSightingList = self.GetMinimalFilteredSightingsList(filter)
            
        sightingFound = False
        
        # for each sighting, test date if necessary. Append new dates to return list.
        for s in filteredSightingList:
            
            # If a single species is specified:
            # since the file is ordered by species taxonomically, we can stop for loop when we've 
            # found a species, processed all its entries, and then moved on to a different species
            # this prevents us from needlessly checking all sightings in the whole database
            if speciesName != "":
                if sightingFound is True:
                    if s["commonName"] != speciesName and speciesName != s["subspeciesName"]:
                        break
                    
            if self.TestSighting(s, filter) is True:
                
                sightingFound = True
                                    
                if queryType == "OnlyLocations":
                    thisLocationList = s["location"]
                
                if queryType == "Checklist":
                    thisLocationList = [s["location"], s["count"], s["checklistID"], s["latitude"]]

                if queryType == "LocationHierarchy":
                    thisLocationList = [s["state"], s["county"], s["location"]]

                # if we're getting first and last dates, too, we need to 
                # store all dates in a dictionary keyed by location
                # so later we can sort them and return the first and last dates, too
                if queryType == "Dates":
                    
                    keyName = s["location"]
                    
                    if keyName not in tempDateDict.keys():
                        tempDateDict[keyName] = [s["date"] + " " + s["time"]]
                    else:
                        tempDateDict[keyName].append(s["date"] + " " + s["time"])
                
                if queryType != "Dates":
                    # add entry to returnList if it's not a duplicate
                    if thisLocationList not in returnList:
                        returnList.append(thisLocationList)
        
        # if we're returning dates, find the first and last dates from dictionary
        # loop through all keys (location names) and append the name and dates
        # to the return list
        if queryType == "Dates":
            for k in tempDateDict.keys():
                tempDateList = tempDateDict[k]
                tempDateList.sort()
                tempFirstDate = tempDateList[0]
                tempLastDate = tempDateList[len(tempDateList) - 1]
                thisLocationList = [k, tempFirstDate, tempLastDate]
                returnList.append(thisLocationList)
        
        # sort the list and return it
        returnList.sort()
        return(returnList)

    def GetNewCountrySpecies(self, filter, filteredSightingList, sightingListForSpeciesSubset, speciesList):
        
        countries = set()
        countrySpecies = []
        tempFilter = deepcopy(filter)
        
        # loop through sightingListForSpeciesSubset to gather relevant country names
        for s in sightingListForSpeciesSubset:
            if self.TestSighting(s, tempFilter) is True:
                countries.add(s["country"])
        countries = list(countries)
        countries.sort()
        
        # loop through countries to gather first-time species sightings
        for country in countries:
            
            # get list of species with first/last dates for specific country filter
            tempFilter.setLocationType("Country")
            tempFilter.setLocationName(country)
            
            speciesWithFirstLastDates = self.GetSpeciesWithData(tempFilter, filteredSightingList)
            
            # use dictionary created when data file was first loaded to get all sightings from 
            # the selected country
            thisCountrySightings = self.countryDict[country]
            
            # create temporary dictionary of sightings in selected country
            # keyed by species name
            tempSpeciesDict = {}
            for tcs in thisCountrySightings:

                commonName = tcs["commonName"]
                
                if commonName not in tempSpeciesDict.keys():
                    tempSpeciesDict[commonName] = [tcs]
                else:
                    tempSpeciesDict[commonName].append(tcs)

            # loop through species with dates to see if any sightings are the 
            # first for the country
            for species in speciesWithFirstLastDates:
                tempSpeciesSightings = tempSpeciesDict[species[0]]
                tempSpeciesSightings = sorted(tempSpeciesSightings, key=lambda x: (x["date"]))
                if species[1] <= tempSpeciesSightings[0]["date"]:
                    countrySpecies.append([country, species[0]])
        
        return(countrySpecies)

    def GetNewCountySpecies(self, filter, filteredSightingList, sightingListForSpeciesSubset, speciesList):
        
        # find which years are in the filtered sightingsfor the species in question
        counties = set()
        countySpecies = []
        tempFilter = deepcopy(filter)

        # loop through speciesWithFirstLastDates to gather county names for sightings subset
        for s in sightingListForSpeciesSubset:
            county = s["county"]
            if self.TestSighting(s, tempFilter) is True:
                if county != "":
                    counties.add(county)
        counties = list(counties)
        counties.sort()
        
        # loop through counties, keeping species that are new sightings
        for county in counties:
            
            # get list of species with first/last dates for filter in selected county
            tempFilter.setLocationType("County")
            tempFilter.setLocationName(county)
            speciesWithFirstLastDates = self.GetSpeciesWithData(tempFilter, filteredSightingList)
            
            thisCountySightings = self.countyDict[county]
            
            # create temporary dictionary of sightings in selected county
            # keyed by species name            
            tempSpeciesDict = {}
            for tms in thisCountySightings:
                commonName = tms["commonName"]
                if commonName not in tempSpeciesDict.keys():
                    tempSpeciesDict[commonName] = [tms]
                else:
                    tempSpeciesDict[commonName].append(tms)

            # loop through species with dates to see if any sightings are the 
            # first for the county
            for species in speciesWithFirstLastDates:
                tempSpeciesSightings = tempSpeciesDict[species[0]]
                tempSpeciesSightings = sorted(tempSpeciesSightings, key=lambda x: (x["date"]))
                if species[1] <= tempSpeciesSightings[0]["date"]:
                    countySpecies.append([county, species[0]])                    
        
        return(countySpecies)

    def GetNewLifeSpecies(self, filter, filteredSightingList, sightingListForSpeciesSubset):
        
        # find which years are in the filtered sightingsfor the species in question
        # DON'T use a SET here, because we want to keep the species taxonomic order 
        lifeSpecies = []
        
        # get list of species with first/last dates for filter
        speciesWithFirstLastDates = self.GetSpeciesWithData(filter, filteredSightingList)

        for species in speciesWithFirstLastDates:
            tempSpeciesSightings = self.speciesDict[species[0]]
            tempSpeciesSightings = sorted(tempSpeciesSightings, key=lambda x: (x["date"]))
            if species[1] <= tempSpeciesSightings[0]["date"]:
                lifeSpecies.append(species[0])        
                        
        return(lifeSpecies)

    def GetNewLocationSpecies(self, filter, filteredSightingList, sightingListForSpeciesSubset, speciesList):
        
        # find which years are in the filtered sightingsfor the species in question
        locations = set()
        locationSpecies = []
        tempFilter = deepcopy(filter)
        
        for s in sightingListForSpeciesSubset:
            if self.TestSighting(s, filter) is True:
                locations.add(s["location"])
        locations = list(locations)
        locations.sort()
        
        # loop through speciesWithFirstLastDates for each state, keeping species that are new
        for location in locations:
            # get list of species with first/last dates for filter                
            tempFilter.setLocationType("Location")
            tempFilter.setLocationName(location)
            
            speciesWithFirstLastDates = self.GetSpeciesWithData(tempFilter, filteredSightingList)
            
            thisLocationSightings = self.locationDict[location]
                        
            tempSpeciesDict = {}
            for tms in thisLocationSightings:
                commonName = tms["commonName"]
                if commonName not in tempSpeciesDict.keys():
                    tempSpeciesDict[commonName] = [tms]
                else:
                    tempSpeciesDict[commonName].append(tms)

            for species in speciesWithFirstLastDates:
                tempSpeciesSightings = tempSpeciesDict[species[0]]
                tempSpeciesSightings = sorted(tempSpeciesSightings, key=lambda x: (x["date"]))
                if species[1] <= tempSpeciesSightings[0]["date"]:
                    locationSpecies.append([location, species[0]])         
                        
        return(locationSpecies)            

    def GetNewMonthSpecies(self, filter, filteredSightingList, sightingListForSpeciesSubset):
        
        # find which months are in the filtered sightingsfor the species in question
        months = set()
        monthSpecies = []
        
        for s in sightingListForSpeciesSubset:
            if self.TestSighting(s, filter) is True:
                months.add(s["date"][5:7])
        months = list(months)
        months.sort()
        
        # get list of species with first/last dates for filter
        for month in months:
            # set temporary filter with each month in loop in filter
            tempFilter = deepcopy(filter)
            tempFilter.setStartSeasonalMonth(month)
            tempFilter.setStartSeasonalDay("01")
            tempFilter.setEndSeasonalMonth(month)
            
            lastDayOfThisMonth = self.GetLastDayOfMonth(month)
            
            tempFilter.setEndSeasonalDay(lastDayOfThisMonth)
            
            speciesWithFirstLastDates = self.GetSpeciesWithData(tempFilter, filteredSightingList)
            
            thisMonthSightings = self.monthDict[month]
            
            tempSpeciesDict = {}
            for tms in thisMonthSightings:
                commonName = tms["commonName"]
                if commonName not in tempSpeciesDict.keys():
                    tempSpeciesDict[commonName] = [tms]
                else:
                    tempSpeciesDict[commonName].append(tms)

            for species in speciesWithFirstLastDates:
                tempSpeciesSightings = tempSpeciesDict[species[0]]
                tempSpeciesSightings = sorted(tempSpeciesSightings, key=lambda x: (x["date"]))
                if species[1] <= tempSpeciesSightings[0]["date"]:
                    monthRange = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                    monthName = monthRange[int(month) - 1]
                    monthSpecies.append([monthName, species[0]])                       
        
        return(monthSpecies)

    def GetNewStateSpecies(self, filter, filteredSightingList, sightingListForSpeciesSubset, speciesList):
        
        # find which years are in the filtered sightingsfor the species in question
        states = set()
        stateSpecies = []
        tempFilter = deepcopy(filter)
        
        for s in sightingListForSpeciesSubset:
            if self.TestSighting(s, tempFilter) is True:
                states.add(s["state"])
        states = list(states)
        states.sort()
        
        # loop through speciesWithFirstLastDates for each state, keeping species that are new
        for state in states:
            # get list of species with first/last dates for filter
            tempFilter.setLocationType("State")
            tempFilter.setLocationName(state)
            
            speciesWithDates = self.GetSpeciesWithData(tempFilter, filteredSightingList)
            thisStateSightings = self.stateDict[state]
            
            tempSpeciesDict = {}
            for tms in thisStateSightings:
                commonName = tms["commonName"]
                if commonName not in tempSpeciesDict.keys():
                    tempSpeciesDict[commonName] = [tms]
                else:
                    tempSpeciesDict[commonName].append(tms)

            for species in speciesWithDates:
                tempSpeciesSightings = tempSpeciesDict[species[0]]
                tempSpeciesSightings = sorted(tempSpeciesSightings, key=lambda x: (x["date"]))
                if species[1] <= tempSpeciesSightings[0]["date"]:
                    stateSpecies.append([state, species[0]])            
                        
        return(stateSpecies)

    def GetNewYearSpecies(self, filter, filteredSightingList, sightingListForSpeciesSubset):
        
        # find which years are in the filtered sightingsfor the species in question
        years = set()
        yearSpecies = []
        thisFilter = deepcopy(filter)
        
        for s in sightingListForSpeciesSubset:
            if self.TestSighting(s, filter) is True:
                years.add(s["date"][0:4])
        years = list(years)
        years.sort()
        
        for year in years:
            thisYearSightings = self.yearDict[year]

            # get list of species with first/last dates for filter
            startDate = year + "-01-01"
            endDate = year + "-12-31"
            thisFilter.setStartDate(startDate)
            thisFilter.setEndDate(endDate)
            speciesWithDates = self.GetSpeciesWithData(thisFilter, filteredSightingList)

            tempSpeciesDict = {}
            for tms in thisYearSightings:
                commonName = tms["commonName"]
                if commonName not in tempSpeciesDict.keys():
                    tempSpeciesDict[commonName] = [tms]
                else:
                    tempSpeciesDict[commonName].append(tms)

            for species in speciesWithDates:
                tempSpeciesSightings = tempSpeciesDict[species[0]]
                tempSpeciesSightings = sorted(tempSpeciesSightings, key=lambda x: (x["date"]))
                if species[1] <= tempSpeciesSightings[0]["date"]:
                    yearSpecies.append([year, species[0]])   
                        
        return(yearSpecies)

    
    def GetQuickEntryCode(self, species):
                
        thisSpecies = deepcopy(species)
        
        if " (" in thisSpecies:
            thisSpecies = thisSpecies.split(" (")[0]
            
        if " x " in thisSpecies:
            return("Not applicable to hybrids")    
            
        cleanedSpeciesName = thisSpecies.replace('-',' ')
        wordList = cleanedSpeciesName.split(" ")
        
        quickEntryCode = ""
        
        if len(wordList) == 1:
            quickEntryCode = wordList[0][0:4]
        
        if len(wordList) == 2:
            quickEntryCode = wordList[0][0:2] + wordList[1][0:2]
            
        if len(wordList) == 3:
            quickEntryCode = wordList[0][0:1] + wordList[1][0:1] + wordList[2][0:2]

        if len(wordList) == 4:
            quickEntryCode = wordList[0][0:1] + wordList[1][0:1] + wordList[2][0:1] + wordList[3][0:1]
                        
        return(quickEntryCode)
    
        
    def GetBBLCode(self, species):
        
        thisScientificName = self.GetScientificName(species)

        if thisScientificName in self.bblCodeDict.keys():                
            bblCode = self.bblCodeDict[thisScientificName]
        else:
            bblCode = ""
        
        return(bblCode)
    

    def GetFamilyName(self, species):
                
        speciesDetails = self.speciesDict[species]
                        
        familyName = speciesDetails[0]["family"]
        
        return(familyName)
    
    
    def GetOrderName(self, species):
        
        speciesDetails = self.speciesDict[species]
                
        orderName = speciesDetails[0]["order"]
        
        return(orderName)   
         
    
    def GetScientificName(self, species):

        speciesDetails = self.speciesDict[species]
        
        scientificName = speciesDetails[0]["scientificName"]
        
        return(scientificName)


    def GetRegionCode(self, longName):
        
        if longName == "**All Regions**":
            return("**All Regions**")
        
        else:
            return(self.regionCodeDict[longName])


    def GetRegionName(self, code):
        
        return(self.regionNameDict[code])
            

    def GetCountryCode(self, longName):
        
        if longName == "**All Countries**":
            return("**All Countries**")
        
        if self.countryStateCodeFileFound is True:
            for l in self.masterLocationList:
                if "countryName" in l.keys():
                    if l["countryName"] == longName:
                        return(l["countryCode"])
        else:
            return(longName) 
                           
                
    def GetStateCode(self, longName):
        
        if longName == "**All States**":
            return("**All States**")
            
        if self.countryStateCodeFileFound is True:
            for l in self.masterLocationList:
                if "stateName" in l.keys():
                    if l["stateName"] == longName:
                        return(l["stateCode"])
        else:
            return(longName)
        

    def GetCountryName(self, shortCode):
        
        if shortCode == "**All Countries**":
            return("**All Countries**")
            
        if self.countryStateCodeFileFound is True:
            for l in self.masterLocationList:
                if l["countryCode"] == shortCode:
                    return(l["countryName"])
        else:
            return(shortCode)


    def GetMonthName(self, monthNumberString):
        
        monthName = self.monthNameDict[monthNumberString]
        return(monthName)
        
        
    def GetStateName(self, shortCode):

        if shortCode == "**All States**":
            return("**All States**")            
        
        if self.countryStateCodeFileFound is True:            
            for l in self.masterLocationList:
                if l["stateCode"] == shortCode:
                    return(l["stateName"])
        else:
            return(shortCode)

        
    def dumpDatabaseToFile(self):
        
        # routine used only in debugging
        f = open("yearbird_Db_Dump.txt", "w+")
        for s in self.sightingList:
            f.write(str(s))
            f.write("\n")
        f.close()
            

    def setStartupFolder(self, startupFolder):
        self.startupFolder = startupFolder


    def getStartupFolder(self):
        return(self.startupFolder)


    def setPhotoDataFile(self, photoDataFile):
        self.photoDataFile = photoDataFile
        

    def getPhotoDataFile(self):
        return(self.photoDataFile)    


    def addPhotoDataToDb(self, photoData):
        
        if photoData["camera"] not in self.cameraList:
            if photoData["camera"] != "":
                self.cameraList.append(photoData["camera"])
                self.cameraList.sort()

        if photoData["lens"] not in self.lensList:
            if photoData["lens"] != "":
                self.lensList.append(photoData["lens"])
                self.lensList.sort()

        if photoData["shutterSpeed"] not in self.shutterSpeedList:
            if photoData["shutterSpeed"] != "":
                self.shutterSpeedList.append(photoData["shutterSpeed"])
                self.shutterSpeedList = natsorted(self.shutterSpeedList, key=lambda y: y.lower(), reverse=True)

        if photoData["aperture"] not in self.apertureList:
            if photoData["aperture"] != "":
                self.apertureList.append(photoData["aperture"])
                self.apertureList= natsorted(self.apertureList, key=lambda y: y.lower())

        if photoData["focalLength"] not in self.focalLengthList:
            if photoData["focalLength"] != "":
                self.focalLengthList.append(photoData["focalLength"])
                self.focalLengthList = natsorted(self.focalLengthList, key=lambda y: y.lower())
                
        if photoData["iso"] not in self.isoList:
            if photoData["iso"] != "":
                self.isoList.append(photoData["iso"])
                self.isoList = natsorted(self.isoList, key=lambda y: y.lower())



    def readPreferences(self):

        prefs_dir = os.path.expanduser("~/Library/Application Support/Yearbird")
        prefs_path = os.path.join(prefs_dir, "yearbirdPreferences.txt")

        if not os.path.isfile(prefs_path):
            return  # No preferences saved yet

        with open(prefs_path, "r") as settingsFile:
            for line in settingsFile:

                if line.startswith("startupFolder="):
                    value = line[len("startupFolder="):].strip()
                    self.startupFolder = value

                elif line.startswith("photoDataFile="):
                    value = line[len("photoDataFile="):].strip()
                    self.photoDataFile = value
                
    
    def writePreferences(self):
        prefs_dir = os.path.expanduser("~/Library/Application Support/Yearbird")
        os.makedirs(prefs_dir, exist_ok=True)

        prefs_path = os.path.join(prefs_dir, "yearbirdPreferences.txt")

        with open(prefs_path, "w") as f:
            f.write("startupFolder=" + self.startupFolder + "\n")
            f.write("photoDataFile=" + self.photoDataFile + "\n")
        
            
