import pytest

from DIRAC.Core.Utilities.ReturnValues import S_OK, S_ERROR, convertToReturnValue, returnValueOrRaise


def test_Ok():
    retVal = S_OK("Hello world")
    assert retVal["OK"] is True
    assert retVal["Value"] == "Hello world"


def test_Error():
    retVal = S_ERROR("This is bad")
    assert retVal["OK"] is False
    assert retVal["Message"] == "This is bad"
    callStack = "".join(retVal["CallStack"])
    assert "Test_ReturnValues" in callStack
    assert "test_Error" in callStack


def test_ErrorWithCustomTraceback():
    retVal = S_ERROR("This is bad", callStack=["My callstack"])
    assert retVal["OK"] is False
    assert retVal["Message"] == "This is bad"
    assert retVal["CallStack"] == ["My callstack"]


class CustomException(Exception):
    pass


@convertToReturnValue
def _happyFunction():
    return {"12345": "Success"}


@convertToReturnValue
def _sadFunction():
    raise CustomException("I am sad")
    return {}


def test_convertToReturnValue():
    retVal = _happyFunction()
    assert retVal["OK"] is True
    assert retVal["Value"] == {"12345": "Success"}
    # Make sure exceptions are captured correctly
    retVal = _sadFunction()
    assert retVal["OK"] is False
    assert "CustomException" in retVal["Message"]
    # Make sure the exception is re-raised
    with pytest.raises(CustomException):
        returnValueOrRaise(_sadFunction())
