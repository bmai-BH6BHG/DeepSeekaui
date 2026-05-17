import subprocess, os, sys
env = os.environ.copy()
env["PYTHONPATH"] = r"H:\deepseekaui\bridge\lib"
env["TMP"] = "H:\\temp"
env["TEMP"] = "H:\\temp"
python = r"C:\Users\陈欣睿\python-sdk\python3.10.16\python.exe"
script = r"H:\deepseekaui\bridge\bridge_server.py"
proc = subprocess.Popen([python, script], cwd=r"H:\deepseekaui", env=env)
print(f"Server PID: {proc.pid}")
proc.wait()
