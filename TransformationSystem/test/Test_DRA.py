"""Test the DataRecoveryAgent"""

import unittest
import sys
from StringIO import StringIO

from mock import MagicMock as Mock, patch

from DIRAC import S_OK, S_ERROR, gLogger

from DIRAC.TransformationSystem.Agent.DataRecoveryAgent import DataRecoveryAgent
from DIRAC.TransformationSystem.Utilities.JobInfo import TaskInfoException

__RCSID__ = "$Id$"

TINFOMOCK = Mock()


class TestDRA(unittest.TestCase):
  """Test the DataRecoveryAgent"""
  dra = None

  @patch("DIRAC.Core.Base.AgentModule.PathFinder", new=Mock())
  @patch("DIRAC.ConfigurationSystem.Client.PathFinder.getSystemInstance", new=Mock())
  @patch("DIRAC.TransformationSystem.Agent.DataRecoveryAgent.ReqClient", new=Mock())
  def setUp(self):
    self.dra = DataRecoveryAgent(agentName="ILCTransformationSystem/DataRecoveryAgent", loadName="TestDRA")
    self.dra.reqClient = Mock()
    self.dra.tClient = Mock()
    self.dra.fcClient = Mock()
    self.dra.jobMon = Mock()
    self.dra.printEveryNJobs = 10

  def tearDown(self):
    pass

  def getTestMock(self):
    """create a JobInfo object with mocks"""
    testJob = Mock(name="jobInfoMock")
    testJob.outputFiles = ["/my/stupid/file.lfn", "/my/stupid/file2.lfn"]
    testJob.outputFileStatus = ["Exists", "Exists"]
    testJob.inputFile = "inputfile.lfn"
    testJob.pendingRequest = False
    testJob.getTaskInfo = Mock()
    return testJob

  @patch("DIRAC.Core.Base.AgentModule.PathFinder", new=Mock())
  @patch("DIRAC.ConfigurationSystem.Client.PathFinder.getSystemInstance", new=Mock())
  @patch("DIRAC.TransformationSystem.Agent.DataRecoveryAgent.ReqClient", new=Mock())
  def test_init(self):
    """test for DataRecoveryAgent initialisation...................................................."""
    res = DataRecoveryAgent(agentName="ILCTransformationSystem/DataRecoveryAgent", loadName="TestDRA")
    self.assertIsInstance(res, DataRecoveryAgent)

  def test_beginExecution(self):
    """test for DataRecoveryAgent beginExecution...................................................."""
    res = self.dra.beginExecution()
    self.assertIn("MCReconstruction", self.dra.transformationTypes)
    self.assertFalse(self.dra.enabled)
    self.assertTrue(res['OK'])

  def test_getEligibleTransformations_success(self):
    """test for DataRecoveryAgent getEligibleTransformations success................................"""
    self.dra.tClient.getTransformations = Mock(
        return_value=S_OK([dict(TransformationID=1234, TransformationName="TestProd12", Type="TestProd")]))

    res = self.dra.getEligibleTransformations(status="Active", typeList=['TestProds'])
    self.assertTrue(res['OK'])
    self.assertIsInstance(res['Value'], dict)
    vals = res['Value']
    self.assertIn("1234", vals)
    self.assertIsInstance(vals['1234'], tuple)
    self.assertEqual(("TestProd", "TestProd12"), vals["1234"])

  def test_getEligibleTransformations_failed(self):
    """test for DataRecoveryAgent getEligibleTransformations failure................................"""
    self.dra.tClient.getTransformations = Mock(return_value=S_ERROR("No can Do"))
    res = self.dra.getEligibleTransformations(status="Active", typeList=['TestProds'])
    self.assertFalse(res['OK'])
    self.assertEqual("No can Do", res['Message'])

  def test_treatProduction1(self):
    """test for DataRecoveryAgent treatProduction success1.........................................."""
    getJobMock = Mock(name="getJobMOck")
    getJobMock.getJobs.return_value = (Mock(name="jobsMOck"), 50, 50)
    tinfoMock = Mock(name="infoMock", return_value=getJobMock)
    self.dra.checkAllJobs = Mock()
    # catch the printout to check path taken
    transInfoDict = dict(TransformationID=1234, TransformationName="TestProd12", Type="TestProd",
                         AuthorDN='/some/cert/owner', AuthorGroup='Test_Prod')
    with patch("%s.TransformationInfo" % MODULE_NAME, new=tinfoMock):
      self.dra.treatProduction(1234, transInfoDict)  # returns None
    # check we start with the summary right away
    for _name, args, _kwargs in self.dra.log.notice.mock_calls:
      self.assertNotIn('Getting Tasks:', str(args))

  def test_treatProduction2(self):
    """test for DataRecoveryAgent treatProduction success2.........................................."""
    getJobMock = Mock(name="getJobMOck")
    getJobMock.getJobs.return_value = (Mock(name="jobsMock"), 50, 50)
    tinfoMock = Mock(name="infoMock", return_value=getJobMock)
    self.dra.checkAllJobs = Mock()
    # catch the printout to check path taken
    transInfoDict = dict(TransformationID=1234, TransformationName="TestProd12", Type="MCSimulation",
                         AuthorDN='/some/cert/owner', AuthorGroup='Test_Prod')
    with patch("%s.TransformationInfo" % MODULE_NAME, new=tinfoMock):
      self.dra.treatProduction(1234, transInfoDict)  # returns None
    self.dra.log.notice.assert_any_call(MatchStringWith("Getting tasks..."))

  def test_treatProduction3(self):
    """test for DataRecoveryAgent treatProduction skip.............................................."""
    getJobMock = Mock(name="getJobMOck")
    getJobMock.getJobs.return_value = (Mock(name="jobsMock"), 50, 50)
    tinfoMock = Mock(name="infoMock", return_value=getJobMock)
    self.dra.checkAllJobs = Mock()
    self.dra.jobCache[1234] = (50, 50)
    # catch the printout to check path taken
    transInfoDict = dict(TransformationID=1234, TransformationName="TestProd12", Type="TestProd",
                         AuthorDN='/some/cert/owner', AuthorGroup='Test_Prod')

    with patch("%s.TransformationInfo" % MODULE_NAME,
               autospec=True,
               return_value=getJobMock):
      self.dra.treatProduction(prodID=1234, transInfoDict=transInfoDict)  # returns None
    self.dra.log.notice.assert_called_with(MatchStringWith("Skipping production 1234"))

  def test_checkJob(self):
    """test for DataRecoveryAgent checkJob MCGeneration............................................."""

    tInfoMock = Mock(name="tInfoMock")

    from DIRAC.TransformationSystem.Utilities.JobInfo import JobInfo

    # Test First option for MCGeneration
    tInfoMock.reset_mock()
    testJob = JobInfo(jobID=1234567, status="Failed", tID=123, tType="MCGeneration")
    testJob.outputFiles = ["/my/stupid/file.lfn"]
    testJob.outputFileStatus = ["Exists"]

    self.dra.checkJob(testJob, tInfoMock)
    self.assertIn("setJobDone", tInfoMock.method_calls[0])
    self.assertEqual(self.dra.todo["MCGeneration"][0]["Counter"], 1)
    self.assertEqual(self.dra.todo["MCGeneration"][1]["Counter"], 0)

    # Test Second option for MCGeneration
    tInfoMock.reset_mock()
    testJob.status = "Done"
    testJob.outputFileStatus = ["Missing"]
    self.dra.checkJob(testJob, tInfoMock)
    self.assertIn("setJobFailed", tInfoMock.method_calls[0])
    self.assertEqual(self.dra.todo["MCGeneration"][0]["Counter"], 1)
    self.assertEqual(self.dra.todo["MCGeneration"][1]["Counter"], 1)

    # Test Second option for MCGeneration
    tInfoMock.reset_mock()
    testJob.status = "Done"
    testJob.outputFileStatus = ["Exists"]
    self.dra.checkJob(testJob, tInfoMock)
    self.assertEqual(tInfoMock.method_calls, [])
    self.assertEqual(self.dra.todo["MCGeneration"][0]["Counter"], 1)
    self.assertEqual(self.dra.todo["MCGeneration"][1]["Counter"], 1)

  def test_checkJob_others(self):
    """test for DataRecoveryAgent checkJob other ProductionTypes ..................................."""

    tInfoMock = Mock(name="tInfoMock")

    from DIRAC.TransformationSystem.Utilities.JobInfo import JobInfo

    ### Test First option for OtherProductions
    tInfoMock.reset_mock()
    testJob = JobInfo(jobID=1234567, status="Failed", tID=123, tType="MCSimulation")
    testJob.outputFiles = ["/my/stupid/file.lfn"]
    testJob.inputFile = "/my/input/file.lfn"
    testJob.outputFileStatus = ["Exists"]
    testJob.otherTasks = True
    self.dra.inputFilesProcessed = set()
    self.dra.checkJob(testJob, tInfoMock)
    self.assertIn(testJob.inputFile, self.dra.inputFilesProcessed)
    self.assertIn("setJobDone", tInfoMock.method_calls[0])
    self.assertIn("setInputProcessed", tInfoMock.method_calls[1])
    self.assertEqual(self.dra.todo["OtherProductions"][0]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][1]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][2]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][3]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][4]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][5]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][6]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][7]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][8]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][9]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][10]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][11]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][12]["Counter"], 0)

    ### Test Second option for OtherProductions
    tInfoMock.reset_mock()
    testJob = JobInfo(jobID=1234567, status="Done", tID=123, tType="MCSimulation")
    testJob.outputFiles = ["/my/stupid/file.lfn"]
    testJob.outputFileStatus = ["Missing"]
    testJob.otherTasks = True
    testJob.inputFile = "/my/inputfile.lfn"
    self.dra.inputFilesProcessed = set([testJob.inputFile])
    self.dra.checkJob(testJob, tInfoMock)
    self.assertIn(testJob.inputFile, self.dra.inputFilesProcessed)
    self.assertIn("setJobFailed", tInfoMock.method_calls[0])
    self.assertEqual(self.dra.todo["OtherProductions"][0]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][1]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][2]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][3]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][4]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][5]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][6]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][7]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][8]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][9]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][10]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][11]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][12]["Counter"], 0)

    ### Test Third option for OtherProductions
    tInfoMock.reset_mock()
    testJob = JobInfo(jobID=1234567, status="Done", tID=123, tType="MCSimulation")
    testJob.outputFiles = ["/my/stupid/file.lfn"]
    testJob.outputFileStatus = ["Exists"]
    testJob.otherTasks = True
    testJob.inputFile = "/my/inputfile.lfn"
    self.dra.inputFilesProcessed = set([testJob.inputFile])
    self.dra.checkJob(testJob, tInfoMock)
    self.assertIn(testJob.inputFile, self.dra.inputFilesProcessed)
    self.assertIn("setJobFailed", tInfoMock.method_calls[0])
    self.assertIn("cleanOutputs", tInfoMock.method_calls[1])
    self.assertEqual(self.dra.todo["OtherProductions"][0]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][1]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][2]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][3]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][4]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][5]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][6]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][7]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][8]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][9]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][10]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][11]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][12]["Counter"], 0)

    ### Test Fourth option for OtherProductions
    tInfoMock.reset_mock()
    testJob = JobInfo(jobID=1234567, status="Done", tID=123, tType="MCSimulation")
    testJob.outputFiles = ["/my/stupid/file.lfn"]
    testJob.outputFileStatus = ["Exists"]
    testJob.otherTasks = False
    testJob.inputFile = "/my/inputfile.lfn"
    testJob.inputFileExists = False
    testJob.fileStatus = "Exists"
    self.dra.inputFilesProcessed = set()
    self.dra.checkJob(testJob, tInfoMock)
    self.assertIn("cleanOutputs", tInfoMock.method_calls[0])
    self.assertIn("setJobFailed", tInfoMock.method_calls[1])
    self.assertIn("setInputDeleted", tInfoMock.method_calls[2])
    self.assertEqual(self.dra.todo["OtherProductions"][0]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][1]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][2]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][3]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][4]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][5]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][6]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][7]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][8]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][9]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][10]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][11]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][12]["Counter"], 0)

    ### Test Fifth option for OtherProductions
    tInfoMock.reset_mock()
    testJob = JobInfo(jobID=1234567, status="Done", tID=123, tType="MCSimulation")
    testJob.outputFiles = ["/my/stupid/file.lfn"]
    testJob.outputFileStatus = ["Exists"]
    testJob.otherTasks = False
    testJob.inputFile = "/my/inputfile.lfn"
    testJob.inputFileExists = False
    testJob.fileStatus = "Deleted"
    self.dra.inputFilesProcessed = set()
    self.dra.checkJob(testJob, tInfoMock)
    self.assertIn("cleanOutputs", tInfoMock.method_calls[0])
    self.assertIn("setJobFailed", tInfoMock.method_calls[1])
    self.assertEqual(self.dra.todo["OtherProductions"][0]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][1]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][2]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][3]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][4]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][5]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][6]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][7]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][8]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][9]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][10]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][11]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][12]["Counter"], 0)

    ### Test sixth option for OtherProductions
    tInfoMock.reset_mock()
    testJob = JobInfo(jobID=1234567, status="Failed", tID=123, tType="MCSimulation")
    testJob.outputFiles = ["/my/stupid/file.lfn"]
    testJob.outputFileStatus = ["Exists"]
    testJob.otherTasks = False
    testJob.inputFile = "/my/inputfile.lfn"
    testJob.inputFileExists = True
    testJob.fileStatus = "Assigned"
    self.dra.inputFilesProcessed = set()
    self.dra._DataRecoveryAgent__failJobHard(testJob, tInfoMock)  # pylint: disable=protected-access, no-member
    gLogger.notice('Expecting calls', infoCalls)
    gLogger.notice('Called', tInfoMock.method_calls)
    assert len(infoCalls) == len(tInfoMock.method_calls)
    for index, infoCall in enumerate(infoCalls):
      self.assertIn(infoCall, tInfoMock.method_calls[index])
    if jStat == 'Done':
      self.assertIn('Failing job %s' % jID, self.dra.notesToSend)
    else:
      self.assertNotIn('Failing job %s' % jID, self.dra.notesToSend)

  def test_notOnlyKeepers(self):
    """ test for __notOnlyKeepers function """

    funcToTest = self.dra._DataRecoveryAgent__notOnlyKeepers  # pylint: disable=protected-access, no-member
    self.assertTrue(funcToTest('MCGeneration'))

    self.dra.todo['InputFiles'][0]['Counter'] = 3  # keepers
    self.dra.todo['InputFiles'][3]['Counter'] = 0
    self.assertFalse(funcToTest("MCSimulation"))

    self.dra.todo['InputFiles'][0]['Counter'] = 3  # keepers
    self.dra.todo['InputFiles'][3]['Counter'] = 3
    self.assertTrue(funcToTest("MCSimulation"))

  def test_checkAllJob(self):
    """test for DataRecoveryAgent checkAllJobs ....................................................."""
    from DIRAC.TransformationSystem.Utilities.JobInfo import JobInfo

    # test with additional task dicts
    from DIRAC.TransformationSystem.Utilities.TransformationInfo import TransformationInfo
    tInfoMock = Mock(name="tInfoMock", spec=TransformationInfo)
    mockJobs = dict([(i, self.getTestMock()) for i in xrange(11)])
    mockJobs[2].pendingRequest = True
    mockJobs[3].getJobInformation = Mock(side_effect=(RuntimeError('ARGJob1'), None))
    mockJobs[4].getTaskInfo = Mock(side_effect=(TaskInfoException('ARG1'), None))
    taskDict = True
    lfnTaskDict = True
    self.dra.checkAllJobs(mockJobs, tInfoMock, taskDict, lfnTaskDict)
    self.dra.log.error.assert_any_call(MatchStringWith('+++++ Exception'), 'ARGJob1')
    self.dra.log.error.assert_any_call(MatchStringWith("Skip Task, due to TaskInfoException: ARG1"))
    self.dra.log.reset_mock()

    ### test inputFile None
    mockJobs = dict([(i, self.getTestMock(nameID=i)) for i in xrange(5)])
    mockJobs[1].inputFiles = []
    mockJobs[1].getTaskInfo = Mock(side_effect=(TaskInfoException("NoInputFile"), None))
    mockJobs[1].tType = "MCSimulation"
    tInfoMock.reset_mock()
    testJob = JobInfo(jobID=1234567, status="Failed", tID=123, tType="MCSimulation")
    testJob.outputFiles = ["/my/stupid/file.lfn"]
    testJob.outputFileStatus = ["Exists"]
    testJob.otherTasks = False
    testJob.inputFile = "/my/inputfile.lfn"
    testJob.inputFileExists = True
    testJob.fileStatus = "Processed"
    self.dra.inputFilesProcessed = set()
    self.dra.checkJob(testJob, tInfoMock)
    self.assertIn("setJobDone", tInfoMock.method_calls[0])
    self.assertEqual(self.dra.todo["OtherProductions"][0]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][1]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][2]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][3]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][4]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][5]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][6]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][7]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][8]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][9]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][10]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][11]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][12]["Counter"], 0)

    ### Test eighth option for OtherProductions
    tInfoMock.reset_mock()
    testJob = JobInfo(jobID=1234567, status="Done", tID=123, tType="MCSimulation")
    testJob.outputFiles = ["/my/stupid/file.lfn"]
    testJob.outputFileStatus = ["Exists"]
    testJob.otherTasks = False
    testJob.inputFile = "/my/inputfile.lfn"
    testJob.inputFileExists = True
    testJob.fileStatus = "Assigned"
    self.dra.inputFilesProcessed = set()
    self.dra.checkJob(testJob, tInfoMock)
    self.assertIn("setInputProcessed", tInfoMock.method_calls[0])
    self.assertEqual(self.dra.todo["OtherProductions"][0]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][1]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][2]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][3]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][4]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][5]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][6]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][7]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][8]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][9]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][10]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][11]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][12]["Counter"], 0)

    ### Test ninth option for OtherProductions
    tInfoMock.reset_mock()
    testJob = JobInfo(jobID=1234567, status="Failed", tID=123, tType="MCSimulation")
    testJob.outputFiles = ["/my/stupid/file.lfn"]
    testJob.outputFileStatus = ["Missing"]
    testJob.otherTasks = False
    testJob.inputFile = "/my/inputfile.lfn"
    testJob.inputFileExists = True
    testJob.fileStatus = "Assigned"
    self.dra.inputFilesProcessed = set()
    self.dra.checkJob(testJob, tInfoMock)
    self.assertIn("setInputUnused", tInfoMock.method_calls[0])
    self.assertEqual(self.dra.todo["OtherProductions"][0]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][1]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][2]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][3]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][4]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][5]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][6]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][7]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][8]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][9]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][10]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][11]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][12]["Counter"], 0)

    ### Test tenth option for OtherProductions
    tInfoMock.reset_mock()
    testJob = JobInfo(jobID=1234567, status="Done", tID=123, tType="MCSimulation")
    testJob.outputFiles = ["/my/stupid/file.lfn"]
    testJob.outputFileStatus = ["Missing"]
    testJob.otherTasks = False
    testJob.inputFile = "/my/inputfile.lfn"
    testJob.inputFileExists = True
    testJob.fileStatus = "Assigned"
    self.dra.inputFilesProcessed = set()
    self.dra.checkJob(testJob, tInfoMock)
    self.assertIn("setInputUnused", tInfoMock.method_calls[0])
    self.assertIn("setJobFailed", tInfoMock.method_calls[1])
    self.assertEqual(self.dra.todo["OtherProductions"][0]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][1]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][2]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][3]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][4]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][5]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][6]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][7]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][8]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][9]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][10]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][11]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][12]["Counter"], 0)

    ### Test eleventh option for OtherProductions
    tInfoMock.reset_mock()
    testJob = JobInfo(jobID=1234567, status="Failed", tID=123, tType="MCSimulation")
    testJob.outputFiles = ["/my/stupid/file.lfn", "/my/stupid/file2.lfn"]
    testJob.outputFileStatus = ["Missing", "Exists"]
    testJob.otherTasks = False
    testJob.inputFile = "/my/inputfile.lfn"
    testJob.inputFileExists = True
    testJob.fileStatus = "Assigned"
    self.dra.inputFilesProcessed = set()
    self.dra.checkJob(testJob, tInfoMock)
    self.assertIn("cleanOutputs", tInfoMock.method_calls[0])
    self.assertIn("setInputUnused", tInfoMock.method_calls[1])
    self.assertEqual(self.dra.todo["OtherProductions"][0]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][1]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][2]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][3]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][4]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][5]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][6]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][7]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][8]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][9]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][10]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][11]["Counter"], 0)
    self.assertEqual(self.dra.todo["OtherProductions"][12]["Counter"], 0)

    ### Test twelfth option for OtherProductions
    tInfoMock.reset_mock()
    testJob = JobInfo(jobID=1234567, status="Done", tID=123, tType="MCSimulation")
    testJob.outputFiles = ["/my/stupid/file.lfn", "/my/stupid/file2.lfn"]
    testJob.outputFileStatus = ["Missing", "Exists"]
    testJob.otherTasks = False
    testJob.inputFile = "/my/inputfile.lfn"
    testJob.inputFileExists = True
    testJob.fileStatus = "Assigned"
    self.dra.inputFilesProcessed = set()
    self.dra.checkJob(testJob, tInfoMock)
    self.assertIn("cleanOutputs", tInfoMock.method_calls[0])
    self.assertIn("setInputUnused", tInfoMock.method_calls[1])
    self.assertIn("setJobFailed", tInfoMock.method_calls[2])
    self.assertEqual(self.dra.todo["OtherProductions"][0]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][1]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][2]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][3]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][4]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][5]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][6]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][7]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][8]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][9]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][10]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][11]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][12]["Counter"], 0)

    ### Test thirteenth option for OtherProductions
    tInfoMock.reset_mock()
    testJob = JobInfo(jobID=1234567, status="Done", tID=123, tType="MCSimulation")
    testJob.outputFiles = ["/my/stupid/file.lfn", "/my/stupid/file2.lfn"]
    testJob.outputFileStatus = ["Missing", "Exists"]
    testJob.otherTasks = False
    testJob.inputFile = "/my/inputfile.lfn"
    testJob.inputFileExists = True
    testJob.fileStatus = "Processed"
    self.dra.inputFilesProcessed = set()
    self.dra.checkJob(testJob, tInfoMock)
    self.assertIn("setJobFailed", tInfoMock.method_calls[0])
    self.assertEqual(self.dra.todo["OtherProductions"][0]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][1]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][2]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][3]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][4]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][5]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][6]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][7]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][8]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][9]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][10]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][11]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][12]["Counter"], 1)

    ### Test fourteenth option for OtherProductions
    tInfoMock.reset_mock()
    testJob = JobInfo(jobID=1234567, status="Strange", tID=123, tType="MCSimulation")
    testJob.outputFiles = ["/my/stupid/file.lfn", "/my/stupid/file2.lfn"]
    testJob.outputFileStatus = ["Missing", "Exists"]
    testJob.otherTasks = False
    testJob.inputFile = "/my/inputfile.lfn"
    testJob.inputFileExists = True
    testJob.fileStatus = "Processed"
    self.dra.inputFilesProcessed = set()
    self.dra.checkJob(testJob, tInfoMock)
    self.assertEqual([], tInfoMock.method_calls)
    self.assertEqual(self.dra.todo["OtherProductions"][0]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][1]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][2]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][3]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][4]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][5]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][6]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][7]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][8]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][9]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][10]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][11]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][12]["Counter"], 1)
    self.assertEqual(self.dra.todo["OtherProductions"][13]["Counter"], 1)

  def test_checkAllJob(self):
    """test for DataRecoveryAgent checkAllJobs ....................................................."""
    from DIRAC.TransformationSystem.Utilities.JobInfo import JobInfo

    ### test with additional task dicts
    out = StringIO()
    sys.stdout = out
    tInfoMock = Mock(name="tInfoMock")
    mockJobs = dict([(i, self.getTestMock()) for i in xrange(11)])
    mockJobs[2].pendingRequest = True
    mockJobs[3].getJobInformation = Mock(side_effect=(RuntimeError("ARGJob1"), None))
    mockJobs[4].getTaskInfo = Mock(side_effect=(TaskInfoException("ARG1"), None))
    taskDict = True
    lfnTaskDict = True
    self.dra.checkAllJobs(mockJobs, tInfoMock, taskDict, lfnTaskDict)
    self.assertIn("ERROR: +++++ Exception:  ARGJob1", out.getvalue().strip())
    self.assertIn("Skip Task, due to TaskInfoException: ARG1", out.getvalue().strip())

    ### test without additional task dicts
    out = StringIO()
    sys.stdout = out
    mockJobs = dict([(i, self.getTestMock()) for i in xrange(5)])
    mockJobs[2].pendingRequest = True
    mockJobs[3].getJobInformation = Mock(side_effect=(RuntimeError("ARGJob2"), None))
    tInfoMock.reset_mock()
    self.dra.checkAllJobs(mockJobs, tInfoMock)
    self.assertIn("ERROR: +++++ Exception:  ARGJob2", out.getvalue().strip())


if __name__ == "__main__":
  SUITE = unittest.defaultTestLoader.loadTestsFromTestCase(TestDRA)
  TESTRESULT = unittest.TextTestRunner(verbosity=3).run(SUITE)
