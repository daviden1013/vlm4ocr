import subprocess
import mkdocs_gen_files

command = ["vlm4ocr", "--help"]

process = subprocess.run(command, capture_output=True, text=True, check=True)
help_text = process.stdout

with mkdocs_gen_files.open("./api/cli.md", "w") as f:
    print("", file=f)
    print("# CLI Reference\n", file=f)
    print("```bash", file=f)
    print(help_text, file=f)
    print("```", file=f)

print("CLI documentation generated successfully.")