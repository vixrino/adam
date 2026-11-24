# Python environment on Windows

We'll first enable **uv** system-wide then describe the process to use it in a project.

## A. Enabling **uv** on Windows

### Requirements

- Windows system with **Administrator** privileges

### 1. Install Python 3.12

Open the **Software Center** and install Python 3.12.

### 2. Install **uv**

In a Powershell terminal, type

```powershell
pip install uv
```
### 3. Authorize **uv**

Open the Windows explorer and type `%APPDATA%` in the path bar. From there, go to `Roaming` > `Python` > `Python312` > `Scripts`. Exact folder names may vary. You should see the **uv** executable sitting there. Copy the folder path.

In the Windows search bar, type `gpedit.msc` and launch the applet under an **Administrator** account. You can also run that command from a terminal with **Administrator** privileges.

Go to `Computer Configuration` > `Windows Settings` > `Security Settings` > `Application Control Policies` > `AppLocker` > `Executable Rules`. Right click on the right panel and click `Create a rule`. Allow executables from the **Script** folder whose path you copied earlier. If asked whether to create default rules, click **Yes**. It may take a few minutes for the new rule to be applied.

### 4. Set up your environment

In a Powershell terminal, add the **Scripts** folder to the `PATH` environment variable:

```powershell
$env:PATH += ";<path to Scripts>"
```

Notice the `;`.

Type `uv` to verify that everything was properly configured.

## B. Setting up a Python project with uv

### 1. Set up your environment

Follow the steps in **A.4**.

### 2. Initialize a **pyproject.toml**

```powershell
uv init
```

### 3. Authorize scripts in the virtual environment

**uv** will create a `.venv` directory at the root of the project for dependencies and local executables. Follow the steps at **A.3** using the relative path `.venv\Scripts` to allow running dev scripts such as **mypy** or **ruff**.

### 4. Set up the repository

Add this to `pyproject.toml`:

```
[tool.uv]
system-certs = true

[[tool.uv.index]]
name = "bdfpypi"
url = "https://bdistrib-build.sofact.banque-france.fr/artifactory/api/pypi/bdf-python-virtual/simple"
default = true
```

### 5. Install dependencies

```powershell
uv add <package>
```
