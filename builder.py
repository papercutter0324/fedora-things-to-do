import session_config
import json
from typing import Dict, Any
import logging

# List of app categories
all_std_categories = ["essential_apps", "internet_apps", "productivity_apps", "multimedia_apps", "gaming_apps", "management_apps", "customization"]
additional_categories = ["internet_apps", "productivity_apps", "multimedia_apps", "gaming_apps", "management_apps", "customization"]

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Change to INFO in production
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# List of placeholders
PLACEHOLDERS = {
    "hostname": "{hostname}",
}

def load_app_data(file_name: str) -> dict:
    try:
        with open(file_name, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"{file_name} not found!")
        return {}
    except json.JSONDecodeError:
        logging.error(f"{file_name} is not a valid JSON file!")
        return {}

def get_option_name(category: str, option: str) -> str:
    distro_data = session_config.get_distro_data()
    logging.debug(f"get_option_name - category: {category}, option: {option}")
    if category == "system_config":
        return distro_data[category][option]["name"]
    elif category in all_std_categories:
        return distro_data[category]["apps"][option]["name"]
    else:
        raise ValueError(f"Unknown category: {category}")

def get_option_description(category: str, option: str) -> str:
    distro_data = session_config.get_distro_data()
    logging.debug(f"get_option_description - category: {category}, option: {option}")
    if category == "system_config":
        return distro_data[category][option]["description"]
    elif category in all_std_categories:
        return distro_data[category]["apps"][option]["description"]
    else:
        raise ValueError(f"Unknown category: {category}")

def generate_options():
    distro_data = session_config.get_distro_data()

    if not distro_data:
        logging.error("No distro data is available!")
        return {}
    
    logging.debug(f"generate_options - distro_data: {distro_data}")
    
    options = {
        "system_config": [key for key in distro_data["system_config"].keys() if key != "description"],
        "essential_apps": [app["name"] for app in distro_data["essential_apps"]["apps"]],
        "internet_apps": {},
        "productivity_apps": {},
        "multimedia_apps": {},
        "gaming_apps": {},
        "management_apps": {},
        "customization": {}
    }
    
    # Loop through the additional categories
    for category in additional_categories:
        category_data = distro_data.get(category, {})
        options[category] = {
            "name": category_data.get("name", ""),
            "apps": list(category_data.get("apps", {}).keys())
        }
    
    logging.debug(f"generate_options - options: {options}")
    return options

def build_system_upgrade(options: Dict[str, Any], output_mode: str) -> str:
    quiet_redirect = " > /dev/null 2>&1" if output_mode == "Quiet" else ""
    
    upgrade_commands = [
        "log_message \"Performing system upgrade... This may take a while...\"",
        f"dnf upgrade -y{quiet_redirect}",
        ""  # Add an empty line for readability
    ]
    
    return "\n".join(upgrade_commands)

def should_quiet_redirect(cmd: str) -> bool:
    no_redirect_patterns = [
        "log_message",
        "echo",
        "printf",
        "read",
        "prompt_",
        "EOF"
    ]
    # Check if the command starts with any of the patterns or contains "EOF"
    return not any(cmd.startswith(pattern) or "EOF" in cmd for pattern in no_redirect_patterns)

# Add this function to check dependencies
def check_dependencies(options: Dict[str, Any]) -> Dict[str, Any]:
    distro_data = session_config.get_distro_data()
    
    # Check if multimedia codecs or GPU codecs are selected
    if any([
        options["system_config"].get("install_multimedia_codecs", False),
        options["system_config"].get("install_intel_codecs", False),
        options["system_config"].get("install_amd_codecs", False)
    ]):
        # Ensure RPM Fusion is enabled
        options["system_config"]["enable_rpmfusion"] = True
    
    return options

# Modify the build_system_config function
def build_system_config(options: Dict[str, Any], output_mode: str) -> str:
    # Check dependencies before building the config
    options = check_dependencies(options)
    config_commands = []
    quiet_redirect = " > /dev/null 2>&1" if output_mode == "Quiet" else ""

    distro_data = session_config.get_distro_data()
    system_config = distro_data["system_config"]

    for option, enabled in options["system_config"].items():
        if enabled and option in system_config:
            description = system_config[option]["description"]
            config_commands.append(f"# {description}")
            commands = system_config[option]["command"]
            if isinstance(commands, list):
                for cmd in commands:
                    if option == "set_hostname" and "hostnamectl set-hostname" in cmd:
                        cmd = f"{cmd} {PLACEHOLDERS['hostname']}"
                    if output_mode == "Quiet" and should_quiet_redirect(cmd):
                        cmd += quiet_redirect
                    config_commands.append(cmd)
            else:
                cmd = commands
                if option == "set_hostname" and "hostnamectl set-hostname" in cmd:
                    cmd = f"{cmd} {PLACEHOLDERS['hostname']}"
                if output_mode == "Quiet" and should_quiet_redirect(cmd):
                    cmd += quiet_redirect
                config_commands.append(cmd)
            config_commands.append("")  # Add an empty line for readability

    return "\n".join(config_commands)

def build_app_install(options: Dict[str, Any], output_mode: str) -> str:
    distro_data = session_config.get_distro_data()
    install_commands = []
    quiet_redirect = " > /dev/null 2>&1" if output_mode == "Quiet" else ""

    # Reusable function for installing apps in any category
    def add_app_install_commands(category: str):
        for category_name, category_data in options.get(category, {}).items():
            category_apps = [app_id for app_id, app_data in category_data.items() if app_data.get('selected', False)]
            if category_apps:
                install_commands.append(f"# Install {distro_data[category][category_name]['name']} applications")

                for app_id in category_apps:
                    app_data = distro_data[category][category_name]['apps'][app_id]
                    install_commands.append(f"log_message \"Installing {app_data['name']}...\"")
                    
                    # Handle if there are multiple installation types
                    if 'installation_types' in app_data:
                        install_type = category_data[app_id]['installation_type']                        
                        if install_type and install_type in app_data['installation_types']:
                            commands = app_data['installation_types'][install_type]['command']
                        else:
                            commands = app_data["command"]
                    else:
                        commands = app_data["command"]

                    # Add commands with quiet_redirect when applicable
                    if isinstance(commands, list):
                        for cmd in commands:
                            install_commands.append(f"{cmd}{quiet_redirect if should_quiet_redirect(cmd) else ''}")
                    else:
                        install_commands.append(f"{commands}{quiet_redirect if should_quiet_redirect(commands) else ''}")

                    install_commands.append(f"log_message \"{app_data['name']} installed successfully.\"")
                
                # Add an empty line for improved readability
                install_commands.append("")

    # Install essential apps separately since it doesn't use the general category structure
    essential_apps = [app for app in distro_data["essential_apps"]["apps"] if options["essential_apps"].get(app["name"], False)]
    if essential_apps:
        install_commands.append("# Install essential applications")
        app_names = " ".join([app["name"] for app in essential_apps])
        install_commands.append(f"log_message \"Installing essential applications...\"")
        install_commands.append(f"dnf install -y {app_names}{quiet_redirect}")
        install_commands.append(f"log_message \"Essential applications installed successfully.\"")
        install_commands.append("")

    # Loop through additional categories
    for category in additional_categories:
        add_app_install_commands(category)

    return "\n".join(install_commands)

def build_custom_script(options: Dict[str, Any], output_mode: str) -> str:
    custom_script = options.get("custom_script", "").strip()
    if custom_script:
        return f"{custom_script}\n"
    return ""