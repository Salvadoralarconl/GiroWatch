"""Local replacement for the Colab upload/download calls used by GiroWatch.

The existing cells use only the selected dictionary's filename, so no file
copy or in-memory upload is necessary. Input files remain unchanged.
"""
from pathlib import Path


class LocalFiles:
    @staticmethod
    def upload():
        print('Select a local file by pasting its full path.')
        while True:
            entered = input('File path: ').strip().strip('"')
            if not entered:
                print('Enter a file path, or press Ctrl+C to cancel.')
                continue
            try:
                path = Path(entered).expanduser().resolve()
                if not path.is_file():
                    print('File not found. Try again.')
                    continue
            except (OSError, ValueError) as error:
                print(f'Cannot access that path: {error}')
                continue
            return {str(path): b''}

    @staticmethod
    def download(filename):
        path = Path(filename).resolve()
        if not path.is_file():
            raise FileNotFoundError(f'Result file not found: {path}')
        print(f'Saved locally at: {path}')


files = LocalFiles()
