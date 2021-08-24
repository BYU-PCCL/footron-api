from ..constants import BASE_URL
from .controller import ControllerApi
from .auth import AuthManager

# TODO: Maybe figure out a better place to put these (is this bad practice?)
controller_api = ControllerApi()
auth_manager = AuthManager(controller_api, BASE_URL)
