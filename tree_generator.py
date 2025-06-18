import os
from pathlib import Path

def generate_tree(directory, prefix="", is_last=True, exclude_dirs=None):
    if exclude_dirs is None:
        exclude_dirs = {'.git', '__pycache__', 'venv', '.pytest_cache', 'node_modules'}
    
    # Get all items in the directory
    items = list(Path(directory).iterdir())
    items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
    
    # Calculate the number of items
    n_items = len(items)
    
    for i, item in enumerate(items):
        # Skip excluded directories
        if item.name in exclude_dirs:
            continue
            
        is_last_item = (i == n_items - 1)
        marker = "└── " if is_last_item else "├── "
        
        # Print the current item
        print(f"{prefix}{marker}{item.name}")
        
        # If it's a directory, recurse
        if item.is_dir():
            new_prefix = prefix + ("    " if is_last_item else "│   ")
            generate_tree(item, new_prefix, is_last_item, exclude_dirs)

def main():
    # Get the current directory
    current_dir = os.getcwd()
    print(f"Project Structure for: {os.path.basename(current_dir)}")
    print("=" * 50)
    generate_tree(current_dir)
    print("=" * 50)

if __name__ == "__main__":
    main() 