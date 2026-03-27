class Filter():
    locationType = ""           # str   choices are Region, Country, County, State, Location, or ""
    locationName = ""           # str   name of region or location  or ""
    startDate = ""              # str   format yyyy-mm-dd  or ""
    endDate = ""                # str   format yyyy-mm-dd  or ""
    startSeasonalMonth = ""     # str   format mm
    startSeasonalDay = ""       # str   format dd
    endSeasonalMonth  = ""      # str   format  mm
    endSeasonalDay  = ""        # str   format dd
    checklistID = ""            # str   number taken from main sightings CSV file
    speciesName = ""            # str    species name
    scientificName = ""
    speciesList = []            # list of species names
    family = ""                 #str  family name
    time = ""                   #str  format HH:MM in 24-hour format
    order = "" 
    commonNameSearch = ""       #str commonNameSearch string

    sightingHasPhoto = ""
    speciesHasPhoto = ""
    validPhotoSpecies = []      # list of species names that are valid according to the photo species filter setting     
    camera = ""
    lens = ""
    startShutterSpeed = ""
    endShutterSpeed = ""
    startAperture = ""
    endAperture = ""
    startFocalLength = ""
    endFocalLength = ""
    startIso = ""
    endIso = ""
    startRating = ""
    endRating = ""  
        
        
    def setLocationType(self,  locationType):
        self.locationType = locationType


    def getLocationType(self):
        return(self.locationType)


    def setLocationName(self,  locationName):
        self.locationName = locationName


    def getLocationName(self):
        return(self.locationName)        

        
    def setStartDate(self,  startDate):
        self.startDate = startDate


    def getStartDate(self):
        return(self.startDate)  


    def setEndDate(self,  endDate):
        self.endDate = endDate


    def getEndDate(self):
        return(self.endDate)   


    def setStartSeasonalMonth(self,  startSeasonalMonth):
        self.startSeasonalMonth = startSeasonalMonth


    def getStartSeasonalMonth(self):
        return(self.startSeasonalMonth)               

        
    def setEndSeasonalMonth(self,  endSeasonalMonth):
        self.endSeasonalMonth = endSeasonalMonth


    def getEndSeasonalMonth(self):
        return(self.endSeasonalMonth)

  
    def setStartSeasonalDay(self,  startSeasonalDay):
        self.startSeasonalDay = startSeasonalDay


    def getStartSeasonalDay(self):
        return(self.startSeasonalDay)


    def setEndSeasonalDay(self,  endSeasonalDay):
        self.endSeasonalDay = endSeasonalDay


    def getEndSeasonalDay(self):
        return(self.endSeasonalDay)

 
    def setChecklistID(self,  checklistID):
        self.checklistID = checklistID


    def getChecklistID(self):
        return(self.checklistID)        


    def setSpeciesName(self,  speciesName):
        self.speciesName = speciesName


    def getSpeciesName(self):
        return(self.speciesName)       


    def setScientificName(self, scientficName):
        self.scientificName = scientficName


    def getScientificName(self):
        return(self.scientificName)  


    def setSpeciesList(self,  speciesList):
        self.speciesList = speciesList


    def getSpeciesList(self):
        return(self.speciesList)           

    
    def setFamily(self,  family):
        self.family = family


    def getFamily(self):
        return(self.family)  
    
    
    def getOrder(self):
        return(self.order)        


    def setOrder(self, order):
        self.order = order


    def getCommonNameSearch(self):
        return(self.commonNameSearch)        


    def setCommonNameSearch(self, commonNameSearch):
        self.commonNameSearch = commonNameSearch

        
    def setTime(self,  time):
        self.time = time

    
    def getTime(self):
        return(self.time)
    

    def setStartRating(self, startRating):
        self.startRating = startRating
        
        
    def getStartRating(self):
        return(self.startRating)


    def setEndRating(self, endRating):
        self.endRating = endRating
        
        
    def getEndRating(self):
        return(self.endRating)
    
    
    def getSightingHasPhoto(self):
        return(self.sightingHasPhoto)    


    def setSpeciesHasPhoto(self, speciesHasPhoto):
        self.speciesHasPhoto = speciesHasPhoto

    
    def getSpeciesHasPhoto(self):
        return(self.speciesHasPhoto)  


    def setValidPhotoSpecies(self, validPhotoSpecies):
        self.validPhotoSpecies = validPhotoSpecies

    
    def getValidPhotoSpecies(self):
        return(self.validPhotoSpecies)  


    def setCamera(self, camera):
        self.camera = camera

    
    def getCamera(self):
        return(self.camera)    


    def setLens(self, lens):
        self.lens = lens

    
    def getLens(self):
        return(self.lens)    

    
    def setStartShutterSpeed(self, startShutterSpeed):
        self.startShutterSpeed = startShutterSpeed

    
    def getStartShutterSpeed(self):
        return(self.startShutterSpeed)    


    def setEndShutterSpeed(self, endShutterSpeed):
        self.endShutterSpeed = endShutterSpeed

    
    def getEndShutterSpeed(self):
        return(self.endShutterSpeed)    


    def setStartAperture(self, startAperture):
        self.startAperture = startAperture

    
    def getStartAperture(self):
        return(self.startAperture)    


    def setEndAperture(self, endAperture):
        self.endAperture = endAperture

    
    def getEndAperture(self):
        return(self.endAperture)        


    def setStartFocalLength(self, startFocalLength):
        self.startFocalLength = startFocalLength

    
    def getStartFocalLength(self):
        return(self.startFocalLength)    


    def setEndFocalLength(self, endFocalLength):
        self.endFocalLength = endFocalLength

    
    def getEndFocalLength(self):
        return(self.endFocalLength)   

    
    def setStartIso(self, startIso):
        self.startIso = startIso

    
    def getStartIso(self):
        return(self.startIso)    


    def setEndIso(self, endIso):
        self.endIso = endIso

    
    def getEndIso(self):
        return(self.endIso)       

        
    def buildWindowTitle(self, prefix, db, count=None, countUnit=""):
        """Return a descriptive MDI child window title for this filter.

        Taxonomy: shows only the most specific level set — species, then family,
        then order.  Location: shows only the single active level (the filter
        only ever carries one at a time).  An optional count and unit label are
        appended in parentheses, e.g. "(42 Species)".
        """
        locationName       = self.getLocationName()
        locationType       = self.getLocationType()
        startDate          = self.getStartDate()
        endDate            = self.getEndDate()
        startSeasonalMonth = self.getStartSeasonalMonth()
        startSeasonalDay   = self.getStartSeasonalDay()
        endSeasonalMonth   = self.getEndSeasonalMonth()
        endSeasonalDay     = self.getEndSeasonalDay()
        speciesName        = self.getSpeciesName()
        family             = self.getFamily()
        order              = self.getOrder()
        commonNameSearch   = self.getCommonNameSearch()

        # Taxonomy: use only the most specific level that has been set
        if speciesName != "":
            taxonomyLabel = speciesName
        elif family != "":
            taxonomyLabel = family[0:family.index("(") - 1] if "(" in family else family
        elif order != "":
            taxonomyLabel = order[0:order.index("(") - 1] if "(" in order else order
        else:
            taxonomyLabel = ""

        windowTitle = taxonomyLabel

        if commonNameSearch != "":
            windowTitle = windowTitle + "; Search: " + commonNameSearch

        # Location: the filter carries at most one active level
        if locationName != "":
            if locationType == "Region":
                locationName = db.GetRegionName(locationName)
            if locationType == "Country":
                locationName = db.GetCountryName(locationName)
            if locationType == "State":
                locationName = db.GetStateName(locationName)
            windowTitle = windowTitle + "; " + locationName

        if startDate != "":
            dateTitle = startDate + " to " + endDate
            if startDate == endDate:
                dateTitle = startDate
            windowTitle = windowTitle + "; " + dateTitle

        if not ((startSeasonalMonth == "") or (endSeasonalMonth == "")):
            monthRange = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            rangeTitle = (monthRange[int(startSeasonalMonth)-1] + "-" + startSeasonalDay +
                          " to " + monthRange[int(endSeasonalMonth)-1] + "-" + endSeasonalDay)
            windowTitle = windowTitle + "; " + rangeTitle

        if windowTitle == "":
            windowTitle = "All species, locations, and dates"

        if windowTitle[0:2] == "; ":
            windowTitle = windowTitle[2:]

        countSuffix = " (" + str(count) + (" " + countUnit if countUnit else "") + ")" if count is not None else ""
        return prefix + ": " + windowTitle + countSuffix


    def debugAll(self):
        returnString = (
            "locationType: " + self.locationType + '   ' +
            "locationName: " + self.locationName + "   " +
            "startDate: " + self.startDate + "   " +
            "endDate: " + self.endDate + "   " +
            "time: " + self.time + "   " +
            "startSeasonalMonth: " + self.startSeasonalMonth + "   " +
            "startSeasonalDay: " + self.startSeasonalDay + "   " +
            "endSeasonalMonth: " + self.endSeasonalMonth + "   " +
            "endSeasonalDay: " + self.endSeasonalDay + "   " +
            "checklistID: " + self.checklistID + "   " +
            "speciesName: " + self.speciesName + "   " +
            "family:" +self.family + "   " + 
            "speciesList:"
            )
        return(returnString,  self.speciesList)
