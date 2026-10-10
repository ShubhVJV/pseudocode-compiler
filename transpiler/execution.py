import subprocess
import tempfile
import os

class ExecutionModule:
    def __init__(self, timeout=5):
        self.timeout = timeout

    def execute(self, code_str, input_data=""):
        # We write code to a temporary file
        # And run it in a subprocess
        fd, temp_path = tempfile.mkstemp(suffix=".py")
        with os.fdopen(fd, 'w') as f:
            f.write(code_str)

        try:
            # We pass input_data to stdin
            result = subprocess.run(
                ["python", temp_path],
                input=input_data,
                text=True,
                capture_output=True,
                timeout=self.timeout
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "error": f"Execution timed out after {self.timeout} seconds."
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e)
            }
        finally:
            os.remove(temp_path)
