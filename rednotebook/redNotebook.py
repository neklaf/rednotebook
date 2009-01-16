#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import with_statement

import sys

#Handle wx specific problems
if not sys.platform == 'win32':
	#should only be called once (at start of program)
	try:
		import wxversion
		wxversion.select("2.8")
	except ImportError:
		pass
import wx

import yaml


import datetime
import os
import zipfile
import operator


if hasattr(sys, "frozen"):
	from rednotebook.util import filesystem
else:
	from util import filesystem
	

print 'AppDir:', filesystem.appDir
baseDir = os.path.abspath(os.path.join(filesystem.appDir, '../'))
print 'BaseDir:', baseDir
if baseDir not in sys.path:
	print 'Adding BaseDir to sys.path'
	sys.path.insert(0, baseDir)
	



#from gui import wxGladeGui
#This version of import is needed for win32 to work
from rednotebook.gui import wxGladeGui
from rednotebook.util import unicode
from rednotebook.util import dates
from rednotebook.util import utils
from rednotebook import info
from rednotebook import config
from rednotebook import export



class RedNotebook(wx.App):
	
	minDate = datetime.date(1970, 1, 1)
	maxDate = datetime.date(2020, 1, 1)
	
	def OnInit(self):
		self.testing = False
		if 'testing' in sys.argv:
			self.testing = True
			print 'Testing Mode'
			filesystem.dataDir = os.path.join(filesystem.redNotebookUserDir, "data-test/")
		
		self.month = None
		self.date = None
		self.months = {}
		
		filesystem.makeDirectories([filesystem.redNotebookUserDir, filesystem.dataDir, filesystem.templateDir])
		self.makeEmptyTemplateFiles()
		filesystem.makeFiles([(filesystem.configFile, '')])
		
		self.config = config.redNotebookConfig(localFilename=filesystem.configFile)
		
		mainFrame = wxGladeGui.MainFrame(self, None, -1, "")
		mainFrame.Show()
		self.SetTopWindow(mainFrame)
		self.frame = mainFrame

		'show instructions at first start or if testing'
		self.firstTimeExecution = not os.path.exists(filesystem.dataDir) or self.testing
		   
		self.actualDate = datetime.date.today()
		
		self.loadAllMonthsFromDisk()
		
		'Nothing to save before first day change'
		self.loadDay(self.actualDate)
		
		self.frame.updateStatistics()
		
		if self.firstTimeExecution is True:
			self.addInstructionContent()

		return True
	
	def getDaysInDateRange(self, range):
		startDate, endDate = range
		assert startDate < endDate
		
		sortedDays = self.sortedDays
		daysInDateRange = []
		for day in sortedDays:
			if day.date < startDate:
				continue
			elif day.date >= startDate and day.date <= endDate:
				daysInDateRange.append(day)
			elif day.date > endDate:
				break
		return daysInDateRange
		
	def _getSortedDays(self):
		return sorted(self.days, dates.compareTwoDays)
	sortedDays = property(_getSortedDays)
	
	def getEditDateOfEntryNumber(self, entryNumber):
		sortedDays = self.sortedDays
		if len(self.sortedDays) == 0:
			return datetime.date.today()
		#entryNumber = utils.restrain(entryNumber, (0, len(sortedDays)-1))
		return dates.getDateFromDay(self.sortedDays[entryNumber % len(sortedDays)])
	
	   
	def makeEmptyTemplateFiles(self):
		def getInstruction(dayNumber):
			return 'The template for this weekday has not been edited. ' + \
					'If you want to have some text that you can add to that day every week, ' + \
					'edit the file "' + filesystem.getTemplateFile(dayNumber) + \
					'" in a text editor.'
					
		fileContentPairs = []
		for dayNumber in range(1, 8):
			fileContentPairs.append((filesystem.getTemplateFile(dayNumber), getInstruction(dayNumber)))
		#templateFiles = map(lambda dayNumber: filesystem.getTemplateFile(dayNumber), range(1, 8))
		
		#fileContentPairs = map(lambda file: (file, ''), templateFiles)
		filesystem.makeFiles(fileContentPairs)
		
	def exportDiary(self):
		self.saveOldDay()
		
		'Create wizard'
		exportWizard = export.ExportWizard(self, 'Export', img_filename='redNotebookIcon/rn-128.png')
		
		'Show the main window'
		exportWizard.run() 
	
		'Cleanup'
		exportWizard.Destroy()
        #export.export(self)
	
	def backupContents(self):
		self.saveToDisk()
		proposedFileName = 'RedNotebook-Backup_' + str(datetime.date.today()) + ".zip"
		dlg = wx.FileDialog(self.frame, "Choose Backup File", '', proposedFileName, "*.zip", wx.SAVE)
		returnValue = dlg.ShowModal()
		dlg.Destroy()
		if returnValue == wx.ID_OK:
			archiveFileName = dlg.GetPath()
			
			if os.path.exists(archiveFileName):
				dialog = wx.MessageDialog(self.frame, "File already exists. Are you sure you want to override it?", 
				"File Exists", wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION) # Create a message dialog box
				if not dialog.ShowModal() == wx.ID_YES:
					return
			
			archiveFiles = []
			for root, dirs, files in os.walk(filesystem.dataDir):
				for file in files:
					archiveFiles.append(os.path.join(root, file))
			
			filesystem.writeArchive(archiveFileName, archiveFiles, filesystem.dataDir)

	
	def saveToDisk(self):
		self.saveOldDay()
		
		for yearAndMonth, month in self.months.iteritems():
			if not month.empty:
				monthFileString = os.path.join(filesystem.dataDir, yearAndMonth + \
											filesystem.fileNameExtension)
				with open(monthFileString, 'w') as monthFile:
					monthContent = {}
					for dayNumber, day in month.days.iteritems():
						'do not add empty days'
						if not day.empty:
							monthContent[dayNumber] = day.content
					#month.prettyPrint()
					yaml.dump(monthContent, monthFile)
		
		self.showMessage('The content has been saved')
		
	def loadAllMonthsFromDisk(self):
		for root, dirs, files in os.walk(filesystem.dataDir):
			for file in files:
				self.loadMonthFromDisk(os.path.join(root, file))
	
	def loadMonthFromDisk(self, path):
		fileName = os.path.basename(path)
		
		try:
			'Get Year and Month from /something/somewhere/2009-01.txt'
			yearAndMonth, extension = os.path.splitext(fileName)
			yearNumber, monthNumber = yearAndMonth.split('-')
			yearNumber = int(yearNumber)
			monthNumber = int(monthNumber)
		except Exception:
			print 'Error:', fileName, 'is an incorrect filename.'
			print 'filenames have to have the following form: 2009-01.txt ' + \
					'for January 2009 (yearWith4Digits-monthWith2Digits.txt)'
			return
		
		monthFileString = path
		
		try:
			'Try to read the contents of the file'
			with open(monthFileString, 'r') as monthFile:
				monthContents = yaml.load(monthFile)
				self.months[yearAndMonth] = Month(yearNumber, monthNumber, monthContents)
		except:
			'If that fails there is nothing to load, so just display an error message'
			print 'An Error occured while loading', fileName
		
		
	
	def loadMonth(self, date):
		
		yearAndMonth = dates.getYearAndMonthFromDate(date)
		
		'Selected month has not been loaded or created yet'
		if not self.months.has_key(yearAndMonth):
			self.months[yearAndMonth] = Month(date.year, date.month)
			
		return self.months[yearAndMonth]
	
	def saveOldDay(self):
		'Order is important'
		self.day.content = self.frame.contentTree.getDayContent()
		self.day.text = self.frame.getDayText()
		self.frame.calendar.setDayEdited(self.date.day, not self.day.empty)
	
	def loadDay(self, newDate):
		oldDate = self.date
		self.date = newDate
		
		if not Month.sameMonth(newDate, oldDate):
			self.month = self.loadMonth(self.date)
			self.frame.calendar.setMonth(self.month)
		
		self.frame.calendar.PySetDate(self.date)
		self.frame.showDay(self.day, self.date)
		self.frame.contentTree.categories = self.nodeNames
		
	def _getCurrentDay(self):
		return self.month.getDay(self.date.day)
	day = property(_getCurrentDay)
	
	def changeDate(self, date):
		self.saveOldDay()
		self.loadDay(date)
		
	def goToNextDay(self):
		self.changeDate(self.date + dates.oneDay)
		
	def goToPrevDay(self):
		self.changeDate(self.date - dates.oneDay)
		
	def goToNextEditedDay(self):
		oldDate = self.date
		self.goToNextDay()
		while self.day.empty and not self.date > self.maxDate:
			self.goToNextDay()
		if self.date > self.maxDate:
			print 'No edited day exists after this one'
			self.changeDate(oldDate)
		
	def goToPrevEditedDay(self):
		oldDate = self.date	
		self.goToPrevDay()
		while not self.day.empty and not self.date < self.minDate:
			self.goToPrevDay()
		if self.date < self.minDate:
			print 'No edited day exists before this one'
			self.changeDate(oldDate)
			
	def showMessage(self, messageText):
		self.frame.showMessageInStatusBar(messageText)
		print messageText
		
	def _getNodeNames(self):
		nodeNames = set([])
		for month in self.months.values():
			nodeNames |= set(month.nodeNames)
		return list(nodeNames)
	nodeNames = property(_getNodeNames)
	
	def search(self, text):
		results = []
		for day in self.days:
			if not day.search(text) == None:
				results.append(day.search(text))
		return results
	
	def _getAllEditedDays(self):
		days = []
		for month in self.months.values():
			daysInMonth = month.days.values()
			
			'Filter out days without content'
			daysInMonth = filter(lambda day: not day.empty, daysInMonth)
			days.extend(daysInMonth)
		return days
	days = property(_getAllEditedDays)
	
	def getTemplateEntry(self, date=None):
		if date is None:
			date = self.date
		weekDayNumber = date.weekday() + 1
		templateFileString = filesystem.getTemplateFile(weekDayNumber)
		try:
			with open(templateFileString, 'r') as templateFile:
				 lines = templateFile.readlines()
				 templateText = reduce(operator.add, lines, '')
				 #templateText.encode('utf-8')
		except IOError, Error:
			print 'Template File', weekDayNumber, 'not found'
			templateText = ''
		return templateText
		
	
	def getNumberOfWords(self):
		#def countWords(day1, day2):
		#	return day1.getNumberOfWords() + day2.getNumberOfWords()
		#return reduce(countWords, self.days, 0)
		numberOfWords = 0
		for day in self.days:
			numberOfWords += day.getNumberOfWords()
		return numberOfWords
	
	def getNumberOfEntries(self):
		return len(self.days)
	
	def getWordCountDict(self):
		wordDict = utils.ZeroBasedDict()
		for day in self.days:
			for word in day.getWords(withSpecialChars=False):
				wordDict[word.lower()] += 1
		return wordDict
			
	
	def addInstructionContent(self):
		instructionDayContent = {u'Cool Stuff': {u'Went to see the pope': None}, 
								 u'Ideas': {u'Invent Anti-Hangover-Machine': None},
								 }
		
		#Dates don't matter as only the categories are shown
		instructionDay = Day(self.actualDate.month, self.actualDate.day, dayContent = instructionDayContent)
		
		self.frame.contentTree.addDayContent(instructionDay)
		self.frame.contentTree.ExpandAll()
		
		instructionText = info.completeWelcomeText
		self.frame.textPanel.showDayText(instructionText)

		
			

class Day(object):
	def __init__(self, month, dayNumber, dayContent = None):
		if dayContent == None:
			dayContent = {}
			
		self.month = month
		self.dayNumber = dayNumber
		self.content = dayContent
	
	#Text
	def _getText(self):
		if self.content.has_key('text'):
			return self.content['text']
		else:
		   return ''
		#self.getContent('text')
	def _setText(self, text):
		self.content['text'] = text
		#self.setContent('text', text)
	text = property(_getText, _setText)
	
	def _hasText(self):
		return len(self.text.strip()) > 0
	hasText = property(_hasText)
	
	def _isEmpty(self):
		if len(self.content.keys()) == 0:
			return True
		elif len(self.content.keys()) == 1 and self.content.has_key('text') and not self.hasText:
			return True
		else:
			return False
	empty = property(_isEmpty)
	
	def getContent(self, key):
		if self.content.has_key(key):
			return self.content[key]
		else:
			return ''
	def setContent(self, key, value):
		self.content[key] = value
		
	def _getTree(self):
		tree = self.content.copy()
		if tree.has_key('text'):
			del tree['text']
		return tree
	tree = property(_getTree)
		
	def _getNodeNames(self):
		return self.tree.keys()
	nodeNames = property(_getNodeNames)
	
	def getCategoryContentPairs(self):
		'''
		Returns a list of (category, contentInCategoryAsList) pairs.
		contentInCategoryAsList can be empty
		'''
		pairs = self.tree.copy()
		for category, content in pairs.iteritems():
			entryList = []
			if content is not None:
				for entry, nonetype in content.iteritems():
					entryList.append(entry)
			pairs[category] = entryList
		return pairs
	
	def getWords(self, withSpecialChars=True):
		if withSpecialChars:
			return self.text.split()
		
		#def stripSpecialCharacters(word):
			#return word.strip('.|-!"/()=?`´*+~#_:;,<>^°{}[]')
		wordList = self.text.split()
		realWords = []
		for word in wordList:
			word = word.strip(u'.|-!"/()=?*+~#_:;,<>^°´`{}[]')
			if len(word) > 0:
				realWords.append(word)
		return realWords
	words = property(getWords)
	
	def getNumberOfWords(self):
		return len(self.words)
	
	
	def search(self, searchText):
		'''Case-insensitive search'''
		upCaseSearchText = searchText.upper()
		upCaseDayText = self.text.upper()
		occurence = upCaseDayText.find(upCaseSearchText)
		
		if occurence > -1:
			spaceSearchLeftStart = occurence-15
			if spaceSearchLeftStart < 0:
				spaceSearchLeftStart = 0
			spaceSearchRightEnd = occurence + len(searchText) + 15
			if spaceSearchRightEnd > len(self.text):
				spaceSearchRightEnd = len(self.text)
				
			resultTextStart = self.text.find(' ', spaceSearchLeftStart, occurence)
			resultTextEnd = self.text.rfind(' ', occurence + len(searchText), spaceSearchRightEnd)
			if resultTextStart == -1:
				resultTextStart = occurence - 10
			if resultTextEnd == -1:
				resultTextEnd = occurence + len(searchText) + 10
				
			return (self, '... ' + unicode.substring(self.text, resultTextStart, resultTextEnd).strip() + ' ...')
		else:
			return None
		
	def _date(self):
		return dates.getDateFromDay(self)
	date = property(_date)
			

class Month(object):
	def __init__(self, yearNumber, monthNumber, monthContent = None):
		if monthContent == None:
			monthContent = {}
		
		self.yearNumber = yearNumber
		self.monthNumber = monthNumber
		self.days = {}
		for dayNumber, dayContent in monthContent.iteritems():
			self.days[dayNumber] = Day(self, dayNumber, dayContent)
	
	def getDay(self, dayNumber):
		if self.days.has_key(dayNumber):
			#print 'Key found', dayNumber
			return self.days[dayNumber]
		else:
			#print 'Key not found', dayNumber
			newDay = Day(self, dayNumber)
			self.days[dayNumber] = newDay
			return newDay
		
	def setDay(self, dayNumber, day):
		self.days[dayNumber] = day
		
	def prettyPrint(self):
		print '***'
		for dayNumber, day in self.days.iteritems():
			print dayNumber, 
			unicode.printUnicode(day.text)
		print '---'
		
	def _isEmpty(self):
		for day in self.days.values():
			if not day.empty:
				return False
		return True
	empty = property(_isEmpty)
	
	def _getNodeNames(self):
		nodeNames = set([])
		for day in self.days.values():
			nodeNames |= set(day.nodeNames)
		return nodeNames
	nodeNames = property(_getNodeNames)
	
	def sameMonth(date1, date2):
		if date1 == None or date2 == None:
			return False
		return date1.month == date2.month and date1.year == date2.year
	sameMonth = staticmethod(sameMonth)
		
	
	
		
	
def main():	
	redNotebook = RedNotebook(redirect=False)
	wx.InitAllImageHandlers()
	redNotebook.MainLoop()

#if __name__ == '__main__':
main()
	
