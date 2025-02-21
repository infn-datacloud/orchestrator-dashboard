CONFIGURATION_PROFILE = "default"

### IAM SETTINGS
IAM_CLIENT_ID = "8f319311-9aa8-4dbe-9d31-b2e0f034ad2e"
IAM_CLIENT_SECRET = "OJZq-oTUCoNmUzdVJcMkE2lEIPRI2sR_aDvT-gwEsGT0idPsTOWIZpduo9tM0Zl2hmJbuFtccylfSEYHgh3xbA"
IAM_BASE_URL = "https://iam.cloud.infn.it"
ORCHESTRATOR_URL = "http://mp-recas.ba.infn.it:8080"
CALLBACK_URL = "https://mp-recas.ba.infn.it:8443/callback"

### TOSCA-related SETTINGS
TOSCA_TEMPLATES_DIR = "/Users/michele/OneDrive/Documenti/Infn-Datacloud/tosca-templates"
SETTINGS_DIR = "/Users/michele/OneDrive/Documenti/Infn-Datacloud/dashboard-configuration"

###"SLAM_URL": "https://paas-dev.cloud.infn.it:8443",
###"CMDB_URL": "https://paas-dev.cloud.infn.it/cmdb",

### DB SETTINGS
SQLALCHEMY_DATABASE_URI = "mysql+pymysql://dashboard:dashboard@localhost/orchestrator_dashboard"
SQLALCHEMY_TRACK_MODIFICATIONS = "False"
SQLALCHEMY_VERSION_HEAD = "88bc3c2c02a6"

### REDIS SETTINGS
REDIS_SOCKET_TIMEOUT = 5

### NOTIFICATION SETTINGS
MAIL_SERVER = "relay-mbox.recas.ba.infn.it"
MAIL_PORT = "25"
MAIL_DEFAULT_SENDER = "admin@orchestrator-dashboard"
MAIL_USERNAME = None
MAIL_PASSWORD = None
MAIL_DEBUG = False

### YOURLS SETTINGS
YOURLS_SITE = None
YOURLS_API_SIGNATURE_TOKEN=None

### ADMIN SETTINGS
SUPPORT_EMAIL = "michele.perniola@ba.infn.it"
ADMINS = "['Michele.Perniola@ba.infn.it']"
EXTERNAL_LINKS = []
OVERALL_TIMEOUT = 720
PROVIDER_TIMEOUT = 720
LOG_LEVEL = "info"
UPLOAD_FOLDER = "/tmp"

FEATURE_ADVANCED_MENU = "no"
FEATURE_UPDATE_DEPLOYMENT = "no"
FEATURE_HIDDEN_DEPLOYMENT_COLUMNS = "4, 5, 7"
FEATURE_HIDDEN_ADMIN_DEPLOYMENT_COLUMNS = ""
FEATURE_VAULT_INTEGRATION = "no"
FEATURE_REQUIRE_USER_SSH_PUBKEY = "no"
FEATURE_PORTS_REQUEST = "no"
FEATURE_S3CREDS_MENU = "no"
FEATURE_ACCESS_REQUEST = "yes"

NOT_GRANTED_ACCESS_TAG = "LOCKED"

S3_IAM_GROUPS = []

SENSITIVE_KEYWORDS = ["password", "token", "passphrase"]

### VAULT INTEGRATION SETTINGS
VAULT_ROLE = "orchestrator"
VAULT_OIDC_AUDIENCE = "ff2c57dc-fa09-43c9-984e-9ad8afc3fb56"

#### LOOK AND FEEL SETTINGS
WELCOME_MESSAGE = "Welcome! This is the PaaS Orchestrator Dashboard"
NAVBAR_BRAND_TEXT = "Dashboard"
NAVBAR_BRAND_ICON = "/static/home/images/indigodc_logo.png"
FAVICON_PATH = "/static/home/images/favicon_io"
MAIL_IMAGE_SRC = "https://raw.githubusercontent.com/maricaantonacci/orchestrator-dashboard/stateful/app/home/static/images/orchestrator-logo.png"
PRIVACY_POLICY_URL = 'http://cookiesandyou.com/'
BRAND_COLOR_1 = "#4c297a"
BRAND_COLOR_2 = "#200e35"

### Template Paths
HOME_TEMPLATE = 'home.html'
PORTFOLIO_TEMPLATE = 'portfolio.html'
MAIL_TEMPLATE = 'email.html'
FOOTER_TEMPLATE = 'footer.html'

UPLOAD_FOLDER = '/opt/uploads'
