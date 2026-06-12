from flask import Blueprint

# Initialize the CRM & TeleCRM blueprint. 
# We set template_folder to point to templates/crm relative to this module.
crm_bp = Blueprint('crm', __name__, template_folder='../templates/crm')

# Import routes and api modules to register them on the blueprint
from crm import auth
from crm import routes_crm
from crm import routes_telecrm
from crm import routes_admin
from crm import api
