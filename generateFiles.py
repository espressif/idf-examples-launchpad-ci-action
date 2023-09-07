import re
import sys
import subprocess
import os
import rtoml
import shutil

# Environment variables
github_repository = os.environ.get('GITHUB_REPOSITORY').split('/')
idf_version = os.environ.get('IDF_VERSION').replace('.', '_')

github_owner = github_repository[0]
github_repo = github_repository[1]

# Root toml object
toml_obj = {'esp_toml_version': 1.0, 'firmware_images_url': f'https://{github_owner}.github.io/{github_repo}/', 'supported_apps': []}

class App:
    
    def __init__(self, app):
        # App directory
        self.app_dir = app
        # Name of the app
        if app:
            self.name = app.split('/')[-1]
        # List of targets (esp32, esp32s2, etc)
        self.targets = []
        # List of tuples (kit, target)
        self.boards = []

current_app = App(None)

# Regex to get the app_dir
def get_app_dir(line):
    return re.search(r'"app_dir":\s*"([^"]*)",', line).group(1) if re.search(r'"app_dir":\s*"([^"]*)",', line) else None

# Regex to get the target
def get_target(line):
    return re.search(r'"target":\s*"([^"]*)",', line).group(1) if re.search(r'"target":\s*"([^"]*)",', line) else None

# Regex to get the kit
def get_kit(line):
    return re.search(r'"config":\s*"([^"]*)",', line).group(1) if re.search(r'"config":\s*"([^"]*)",', line) else None

# Squash the json into a list of apps
def squash_json(input_str):
    global current_app
    # Split the input into lines
    lines = input_str.splitlines()
    output_list = []
    for line in lines:
        # Get the app_dir
        app = get_app_dir(line)
        # If its a not a None and not the same as the current app
        if current_app.app_dir != app:
            # Save the previous app
            if current_app.app_dir:
                output_list.append(current_app.__dict__)
            current_app = App(app)

        # If we are building for a kit        
        if (get_kit(line) != ''):
            current_app.boards.append((get_kit(line), get_target(line)))
        # If we are building for targets
        else:
            current_app.targets.append(get_target(line))

    # Append last app
    output_list.append(current_app.__dict__)
    
    return output_list

# Merge binaries for each app
def merge_binaries(apps):
    os.makedirs('binaries', exist_ok=True)
    for app in apps:
        # If we are merging binaries for kits
        if app.get('boards'):
            for board in app['boards']:
                kit = board[0]
                target = board[1]
                cmd = ['esptool.py', '--chip', target, 'merge_bin', '-o', f'{app["name"]}-{kit}-{target}-{idf_version}.bin', '@flash_args']
                cwd = f'{app.get("app_dir")}/build_{kit}'
                subprocess.run(cmd, cwd=cwd)
                print(f'Merged binaries for {app["name"]}-{kit}-{target}-{idf_version}.bin')
                shutil.move(f'{cwd}/{app["name"]}-{kit}-{target}-{idf_version}.bin', 'binaries')
        # If we are merging binaries for targets
        else:
            for target in app['targets']:            
                cmd = ['esptool.py', '--chip', target, 'merge_bin', '-o', f'{app["name"]}-{target}-{idf_version}.bin', '@flash_args']
                cwd = f'{app.get("app_dir")}/build'
                subprocess.run(cmd, cwd=cwd)
                print(f'Merged binaries for {app["name"]}-{target}-{idf_version}.bin')
                shutil.move(f'{cwd}/{app["name"]}-{target}-{idf_version}.bin', 'binaries')

# Write a single app to the toml file
def write_app(app):
    # If we are working with kits
    if app.get('boards'):
        for board in app['boards']:
            kit = board[0]
            target = board[1]
            toml_obj[f'{app["name"]}-{kit}-{idf_version}'] = {}
            toml_obj[f'{app["name"]}-{kit}-{idf_version}']['chipsets'] = [target]
            toml_obj[f'{app["name"]}-{kit}-{idf_version}'][f'image.{target}'] = f'{app["name"]}-{kit}-{target}-{idf_version}.bin'
            toml_obj[f'{app["name"]}-{kit}-{idf_version}']['android_app_url'] = ''
            toml_obj[f'{app["name"]}-{kit}-{idf_version}']['ios_app_url'] = ''
    # If we are working with targets
    else:
        toml_obj[f'{app["name"]}-{idf_version}'] = {}
        toml_obj[f'{app["name"]}-{idf_version}']['chipsets'] = app['targets']
        for target in app['targets']:
            toml_obj[f'{app["name"]}-{idf_version}'][f'image.{target}'] = f'{app["name"]}-{target}-{idf_version}.bin' 
        toml_obj[f'{app["name"]}-{idf_version}']['android_app_url'] = ''
        toml_obj[f'{app["name"]}-{idf_version}']['ios_app_url'] = ''

# Create the config.toml file
def create_config_toml(apps):
    for app in apps:
            if app.get('boards'):
                toml_obj['supported_apps'].extend([f'{app["name"]}-{board[0]}-{idf_version}' for board in app['boards']])
            else:
                toml_obj['supported_apps'].extend([f'{app["name"]}-{idf_version}'])
            for app in apps:
                write_app(app)

            with open('binaries/config.toml', 'w') as toml_file:
                rtoml.dump(toml_obj, toml_file)

            # This is a workaround to remove the quotes around the image.<string> in the config.toml file as dot is not allowed in the key by default            
            with open('binaries/config.toml', 'r') as toml_file:
                fixed = replace_image_string(toml_file.read())

            with open('binaries/config.toml', 'w') as toml_file:
                toml_file.write(fixed)

def replace_image_string(text):
    # Define the regular expression pattern to find "image.<string>"
    pattern = r'"(image\.\w+)"'
    # Use re.sub() to replace the matched pattern with image.<string>
    result = re.sub(pattern, r'\1', text)
    return result

# Get the output json file from idf_build_apps, process it, merge binaries and create config.toml
with open(sys.argv[1], 'r') as file:
    apps = squash_json(file.read())
    merge_binaries(apps)
    create_config_toml(apps)
