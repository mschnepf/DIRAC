"""
Data recovery agent: sets as unused files that are really undone.

    In general for data processing productions we need to completely abandon the 'by hand'
    reschedule operation such that accidental reschedulings don't result in data being processed twice.

    For all above cases the following procedure should be used to achieve 100%:

    - Starting from the data in the Production DB for each transformation
      look for files in the following status:
         Assigned
         MaxReset
      some of these will correspond to the final WMS status 'Failed'.

    For files in MaxReset and Assigned:
    - Discover corresponding job WMS ID
    - Check that there are no outstanding requests for the job
      o wait until all are treated before proceeding
    - Check that none of the job input data has BK descendants for the current production
      o if the data has a replica flag it means all was uploaded successfully - should be investigated by hand
      o if there is no replica flag can proceed with file removal from LFC / storage (can be disabled by flag)
    - Mark the recovered input file status as 'Unused' in the ProductionDB


New Plan:

getTransformations
getFailedJobsOfTheTransformation
- makeSureNoPendingRequests
getInputFilesForthejobs
- checkIfInputFile Assigned or MaxReset
getOutputFilesForTheJobs
- Make Sure no Descendents of the outputfiles?
- Check if _all_ or _no_ outputfiles exist
Send notification about changes

??Cache the jobs for 24hours, will depend on performance

"""


__RCSID__ = "$Id$"
__VERSION__ = "$Revision: $"

from DIRAC import gLogger, S_OK, S_ERROR
from DIRAC.Core.Base.AgentModule import AgentModule
from DIRAC.RequestManagementSystem.Client.ReqClient import ReqClient
from DIRAC.Core.Utilities.List import uniqueElements
from DIRAC.Core.Utilities.Time import dateTime
from DIRAC.Core.Workflow.Workflow import fromXMLString
from DIRAC.Resources.Catalog.FileCatalogClient import FileCatalogClient
from DIRAC.ConfigurationSystem.Client.Helpers.Operations import Operations

from DIRAC.TransformationSystem.Client.TransformationClient import TransformationClient
from ILCDIRAC.Core.Utilities.ProductionData import constructProductionLFNs

import datetime

AGENT_NAME = 'ILCTransformation/DataRecoveryAgent'


class DataRecoveryAgent(AgentModule):
  """Data Recovery Agent"""
  def __init__(self, *args, **kwargs):
    AgentModule.__init__(self, *args, **kwargs)
    self.name = 'DataRecoveryAgent'
    self.log = gLogger.getSubLogger("DataRecoveryAgent")
    self.enableFlag = False
    self.transClient = None
    self.requestClient = None
    self.taskIDName = ''
    self.externalStatus = ''
    self.externalID = ''
    self.ops = None
    self.removalOKFlag = False

    self.fileSelectionStatus = ['Assigned', 'MaxReset']
    self.updateStatus = 'Unused'
    self.wmsStatusList = ['Failed']
    #only worry about files > 12hrs since last update
    self.selectDelay = self.am_getOption("Delay", 12)  # hours
    self.ignoreLessThan = self.ops.getValue("Transformations/IgnoreLessThan", '724')
    self.transformationTypes = self.am_getOption(
        "TransformationTypes", [
            'MCReconstruction', 'MCSimulation', 'MCReconstruction_Overlay', 'Merge'])
    self.transformationStatus = self.am_getOption("TransformationStatus", ['Active', 'Completing'])

    #############################################################################
  def initialize(self):
    """Sets defaults
    """
    self.transClient = TransformationClient()
    self.requestClient = ReqClient()
    self.taskIDName = 'TaskID'
    self.externalStatus = 'ExternalStatus'
    self.externalID = 'ExternalID'
    self.am_setOption('PollingTime', 2 * 60 * 60)  # no stalled jobs are considered so can be frequent
    self.enableFlag = self.am_getOption('EnableFlag', False)
    self.am_setModuleParam("shifterProxy", "ProductionManager")
    self.ops = Operations()
    return S_OK()
  #############################################################################

  def execute(self):
    """ The main execution method.
    """
    self.log.info('Enable flag is %s' % self.enableFlag)
    self.removalOKFlag = False

    transformationDict = {}
    for transStatus in self.transformationStatus:
      result = self.getEligibleTransformations(transStatus, self.transformationTypes)
      if not result['OK']:
        self.log.error(result)
        return S_ERROR('Could not obtain eligible transformations for status "%s"' % (transStatus))

      if not result['Value']:
        self.log.info('No "%s" transformations of types %s to process.' %
                      (transStatus, ", ".join(self.transformationTypes)))
        continue

      transformationDict.update(result['Value'])
    transformationTypesString = ', '.join(self.transformationTypes)
    self.log.info('Selected %s transformations of types %s' %
                  (len(transformationDict.keys()), transformationTypesString))
    self.log.verbose('The following transformations were selected out of %s:\n%s' %
                     (transformationTypesString, ', '.join(transformationDict.keys())))

    #initially this was useful for restricting the considered list
    #now we use the DataRecoveryAgent in setups where IDs are low
    tDict = transformationDict
    if self.ignoreLessThan:
      for trafo in tDict:
        if int(trafo) < int(self.ignoreLessThan):
          del transformationDict[trafo]
          self.log.verbose(
              'Ignoring transformation %s ( is less than specified limit %s )' %
              (trafo, self.ignoreLessThan))

    for transformation, typeName in transformationDict.items():
      res = self.treatTransformation(transformation, typeName)
      if not res['OK'] and res['Message']:
        self.log.error("treatTransformation error", res['Message'])

    return S_OK()

  #############################################################################
  def getEligibleTransformations(self, status, typeList):
    """ Select transformations of given status and type.
    """
    res = self.transClient.getTransformations(condDict={'Status': status, 'Type': typeList})
    if not res['OK']:
      return res
    transformations = {}
    for prod in res['Value']:
      prodID = prod['TransformationID']
      transformations[str(prodID)] = prod['Type']
    return S_OK(transformations)

  #############################################################################
  def selectTransformationFiles(self, transformation, statusList):
    """ Select files, production jobIDs in specified file status for a given transformation.
    """
    #Until a query for files with timestamp can be obtained must rely on the
    #WMS job last update
    res = self.transClient.getTransformationFiles(condDict={'TransformationID': transformation, 'Status': statusList})
    self.log.debug(res)
    if not res['OK']:
      return res
    resDict = {}
    for fileDict in res['Value']:
      if 'LFN' not in fileDict or self.taskIDName not in fileDict or 'LastUpdate' not in fileDict:
        self.log.info('LFN, %s and LastUpdate are mandatory, >=1 are missing for:\n%s' % (self.taskIDName, fileDict))
        continue
      lfn = fileDict['LFN']
      jobID = fileDict[self.taskIDName]
      resDict[lfn] = jobID
    if resDict:
      self.log.info('Selected %s files overall for transformation %s' % (len(resDict.keys()), transformation))
    return S_OK(resDict)

  #############################################################################
  def obtainWMSJobIDs(self, transformation, fileDict, selectDelay, wmsStatusList):
    """ Group files by the corresponding WMS jobIDs, check the corresponding
        jobs have not been updated for the delay time.  Can't get into any
        mess because we start from files only in MaxReset / Assigned and check
        corresponding jobs.  Mixtures of files for jobs in MaxReset and Assigned
        statuses only possibly include some files in Unused status (not Processed
        for example) that will not be touched.
    """
    prodJobIDs = uniqueElements(fileDict.values())
    self.log.info('The following %s production jobIDs apply to the selected files:\n%s' % (len(prodJobIDs), prodJobIDs))

    jobFileDict = {}
    condDict = {'TransformationID': transformation, self.taskIDName: prodJobIDs}
    olderThan = dateTime() - datetime.timedelta(hours=selectDelay)

    res = self.transClient.getTransformationTasks(condDict=condDict, older=olderThan,
                                                  timeStamp='LastUpdateTime', inputVector=True)
    self.log.debug(res)
    if not res['OK']:
      self.log.error('getTransformationTasks returned an error:\n%s' % res['Message'])
      return res

    for jobDict in res['Value']:
      missingKey = False
      for key in [self.taskIDName, self.externalID, 'LastUpdateTime', self.externalStatus, 'InputVector']:
        if key not in jobDict:
          self.log.info('Missing key %s for job dictionary, the following is available:\n%s' % (key, jobDict))
          missingKey = True
          continue

      if missingKey:
        continue

      job = jobDict[self.taskIDName]
      wmsID = jobDict[self.externalID]
      lastUpdate = jobDict['LastUpdateTime']
      wmsStatus = jobDict[self.externalStatus]
      jobInputData = jobDict['InputVector']
      jobInputData = [lfn.replace('LFN:', '') for lfn in jobInputData.split(';')]

      if not int(wmsID):
        self.log.info('Prod job %s status is %s (ID = %s) so will not recheck with WMS' % (job, wmsStatus, wmsID))
        continue

      self.log.info(
          'Job %s, prod job %s last update %s, production management system status %s' %
          (wmsID, job, lastUpdate, wmsStatus))
      #Exclude jobs not having appropriate WMS status - have to trust that production management status is correct
      if wmsStatus not in wmsStatusList:
        self.log.info('Job %s is in status %s, not %s so will be ignored' %
                      (wmsID, wmsStatus, ', '.join(wmsStatusList)))
        continue

      finalJobData = []
      #Must map unique files -> jobs in expected state
      for lfn, prodID in fileDict.items():
        if int(prodID) == int(job):
          finalJobData.append(lfn)

      self.log.info('Found %s files for job %s' % (len(finalJobData), job))
      jobFileDict[wmsID] = finalJobData

    return S_OK(jobFileDict)

  #############################################################################
  def checkOutstandingRequests(self, jobFileDict):
    """ Before doing anything check that no outstanding requests are pending
        for the set of WMS jobIDs.
    """
    jobs = jobFileDict.keys()

    result = self.requestClient.readRequestsForJobs(jobs)
    if not result['OK']:
      return result

    if not result['Value']:
      self.log.info('None of the jobs have pending requests')
      return S_OK(jobFileDict)

    for jobID, reqVal in result['Value']['Successful'].iteritems():
      if not reqVal:  # if reqVal is empty there is no request
        del jobFileDict[str(jobID)]
      self.log.info('Removing jobID %s from consideration until requests are completed' % (jobID))

    return S_OK(jobFileDict)

  ############################################################################
  def checkDescendents(self, transformation, filedict, jobFileDict):
    """ look that all jobs produced, or not output
    """
    res = self.transClient.getTransformationParameters(transformation, ['Body'])
    if not res['OK']:
      self.log.error('Could not get Body from TransformationDB')
      return res
    body = res['Value']
    workflow = fromXMLString(body)
    workflow.resolveGlobalVars()

    olist = []
    for step in workflow.step_instances:
      param = step.findParameter('listoutput')
      if not param:
        continue
      olist.extend(param.value)
    expectedlfns = []
    contactfailed = []
    fileprocessed = []
    files = []
    tasks_to_be_checked = {}
    for files in jobFileDict.values():
      for myFile in files:
        if myFile in filedict:
          tasks_to_be_checked[myFile] = filedict[myFile]  # get the tasks that need to be checked
    for filep, task in tasks_to_be_checked.items():
      commons = {'outputList': olist,
                 'PRODUCTION_ID': transformation,
                 'JOB_ID': task,
                 }
      out = constructProductionLFNs(commons)
      expectedlfns = out['Value']['ProductionOutputData']
      fcClient = FileCatalogClient()
      res = fcClient.getFileMetadata(expectedlfns)
      if not res['OK']:
        self.log.error('Getting metadata failed')
        contactfailed.append(filep)
        continue
      if filep not in files:
        files.append(filep)
      success = res['Value']['Successful'].keys()
      failed = res['Value']['Failed'].keys()
      if len(success) and not len(failed):
        fileprocessed.append(filep)

    final_list_unused = [unusedFile for unusedFile in files if unusedFile not in fileprocessed]

    result = {'filesprocessed': fileprocessed, 'filesToMarkUnused': final_list_unused}
    return S_OK(result)

  #############################################################################
  def updateFileStatus(self, transformation, fileList, fileStatus):
    """ Update file list to specified status.
    """
    if not self.enableFlag:
      self.log.info(
          'Enable flag is False, would update  %s files to "%s" status for %s' %
          (len(fileList), fileStatus, transformation))
      return S_OK()

    self.log.info('Updating %s files to "%s" status for %s' % (len(fileList), fileStatus, transformation))
    result = self.transClient.setFileStatusForTransformation(int(transformation), fileStatus, fileList, force = True)
    self.log.debug(result)
    if not result['OK']:
      self.log.error(result['Message'])
      return result
    if result['Value'] and 'Failed' in result['Value']:
      self.log.error(result['Value']['Failed'])
      return result

    msg = result['Value']
    for lfn, message in msg.items():
      self.log.info('%s => %s' % (lfn, message))

    return S_OK()

  def treatTransformation(self, transformation, typeName):
    """treat the transformation"""
    self.log.info('=' * len('Looking at transformation %s type %s:' % (transformation, typeName)))
    self.log.info('Looking at transformation %s:' % (transformation))

    result = self.selectTransformationFiles(transformation, self.fileSelectionStatus)
    if not result['OK']:
      self.log.error("Could not select files for transformation", str(transformation))
      self.log.error(result['Message'])
      return S_ERROR()

    if not result['Value']:
      self.log.info('No files in status %s selected for transformation %s' %
                    (', '.join(self.fileSelectionStatus), transformation))
      return S_OK()

    fileDict = result['Value']
    result = self.obtainWMSJobIDs(transformation, fileDict, self.selectDelay, self.wmsStatusList)
    if not result['OK']:
      self.log.error(result['Message'])
      self.log.error('Could not obtain WMS jobIDs for files of transformation', str(transformation))
      return S_ERROR()

    if not result['Value']:
      self.log.info('No eligible WMS jobIDs found for %s files in list:\n%s ...' %
                    (len(fileDict.keys()), fileDict.keys()[0]))
      return S_OK()

    jobFileDict = result['Value']

    for job, lfns in jobFileDict.iteritems():
      res = self.treatJobFile(job, lfns, transformation)
      if not res['OK']:
        self.log.error('TreatJobFile Error', res['Message'])

  def treatJobFile(self, wmsID, lfns, transformation):
    """deal with individual jobs, if a failed job did indeed process a file, set the job to Done"""
    jobFileDict = {wmsID: lfns}
    fileCount = 0
    for lfnList in jobFileDict.values():
      fileCount += len(lfnList)

    if not fileCount:
      self.log.info('No files were selected for transformation %s after examining WMS jobs.' % transformation)
      return S_OK()

    self.log.info('%s files are selected after examining related WMS jobs' % (fileCount))
    result = self.checkOutstandingRequests(jobFileDict)
    if not result['OK']:
      self.log.error(result['Message'])
      return S_ERROR()

    if not result['Value']:
      self.log.info('No WMS jobs without pending requests to process.')
      return S_OK()

    jobFileNoRequestsDict = result['Value']
    fileCount = 0
    for lfnList in jobFileNoRequestsDict.values():
      fileCount += len(lfnList)

    self.log.info('%s files are selected after removing any relating to jobs with pending requests' % (fileCount))
    result = self.checkDescendents(transformation, fileDict, jobFileNoRequestsDict)
    if not result['OK']:
      self.log.error(result['Message'])
      return S_ERROR()

    jobsWithFilesOKToUpdate = result['Value']['filesToMarkUnused']
    jobsWithFilesProcessed = result['Value']['filesprocessed']
    self.log.info('====> Transformation %s total files that can be updated now: %s' %
                  (transformation, len(jobsWithFilesOKToUpdate)))

    filesToUpdateUnused = []
    for fileList in jobsWithFilesOKToUpdate:
      filesToUpdateUnused.append(fileList)

    filesToUpdateProcessed = []
    for fileList in jobsWithFilesProcessed:
      filesToUpdateProcessed.append(fileList)

    if not self.removalOKFlag:
      self.log.info("Will not change file status: RemovalOK False")
      self.log.info("Files to processed %s " % ", ".join(filesToUpdateProcessed))
      self.log.info("Files to unused %s " % ", ".join(filesToUpdateUnused))
      return S_OK()

    if filesToUpdateUnused and self.removalOKFlag:
      result = self.updateFileStatus(transformation, filesToUpdateUnused, self.updateStatus)
      if not result['OK']:
        self.log.error('Recoverable files were not updated with result:\n%s' % (result['Message']))
        return S_ERROR()
    else:
      self.log.info('There are no files with failed jobs to update for production %s in this cycle' % transformation)

    if filesToUpdateProcessed and self.removalOKFlag:
      result = self.updateFileStatus(transformation, filesToUpdateProcessed, 'Processed')
      if not result['OK']:
        self.log.error('Recoverable files were not updated with result:\n%s' % (result['Message']))
        return S_ERROR()
    else:
      self.log.info('There are no files processed to update for production %s in this cycle' % transformation)
