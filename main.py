"""Start GiroWatch's existing workflows locally in a terminal."""
from pathlib import Path
import os
import runpy


def main():
    project_folder = Path(__file__).resolve().parent
    # Relative profile and results paths always refer to this project.
    os.chdir(project_folder)
    stages = {
        '1': ('Run grouping', 'run_groups.py'),
        '2': ('Order grouping', 'order_groups.py'),
        '3': ('Error review', 'error_review.py')
    }
    while True:
        print('\nGiroWatch')
        for number, (label, _) in stages.items():
            print(f'{number}: {label}')
        print('0: Exit')
        choice = input('Choose a stage: ').strip()
        if choice == '0':
            break
        if choice not in stages:
            print('Choose 1, 2, 3, or 0.')
            continue
        try:
            runpy.run_path(str(project_folder / stages[choice][1]), run_name='__main__')
        except KeyboardInterrupt:
            print('\nStage cancelled. Returning to the menu.')
        except (ValueError, OSError) as error:
            print(f'Could not complete this stage: {error}')


if __name__ == '__main__':
    main()
