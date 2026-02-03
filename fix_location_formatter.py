#!/usr/bin/env python3
"""
Fix all React components to remove locationFormatter usage
"""

import os
import re

# Base directory
base_dir = "trialreact/src"

# Files to update with their patterns
files_to_fix = [
    {
        "file": "pages/Heads/HeadApprovalDetails.jsx",
        "import_pattern": r'import\s*{\s*formatLocationDisplay\s*}\s*from\s*[\'"]\.\.?/.*?locationFormatter[\'"];?\n?',
        "usage_patterns": [
            (r'formatLocationDisplay\(([^)]+)\)', r'\1.destination'),
        ]
    },
    {
        "file": "pages/Employee/EmployeeLiquidation.jsx", 
        "import_pattern": r'import\s*{\s*formatLocationDisplay\s*}\s*from\s*[\'"]\.\.?/.*?locationFormatter[\'"];?\n?',
        "usage_patterns": [
            (r'formatLocationDisplay\(([^)]+\|\|[^)]+)\)', r'(\1)?.destination'),
        ]
    },
    {
        "file": "components/TravelOrderFormSteps/ValidationStep.jsx",
        "import_pattern": r'import\s*{\s*formatLocationDisplay\s*}\s*from\s*[\'"]\.\.?/.*?locationFormatter[\'"];?\n?',
        "usage_patterns": [
            (r'formatLocationDisplay\(([^)]+)\)', r'\1.destination'),
        ]
    },
    {
        "file": "pages/Accountant/AccountantReview.jsx",
        "import_pattern": r'import\s*{\s*formatLocationDisplay\s*}\s*from\s*[\'"]\.\.?/.*?locationFormatter[\'"];?\n?',
        "usage_patterns": [
            (r'formatLocationDisplay\(([^)]+\.travel_order)\)', r'\1?.destination'),
        ]
    },
    {
        "file": "components/ViewApproval.jsx",
        "import_pattern": r'import\s*{\s*formatLocationDisplay\s*}\s*from\s*[\'"]\.\.?/.*?locationFormatter[\'"];?\n?',
        "usage_patterns": [
            (r'formatLocationDisplay\(([^)]+)\)', r'\1.destination'),
        ]
    },
    {
        "file": "pages/Employee/MyTravels.jsx",
        "import_pattern": r'import\s*{\s*formatLocationDisplay\s*}\s*from\s*[\'"]\.\.?/.*?locationFormatter[\'"];?\n?',
        "usage_patterns": [
            (r'formatLocationDisplay\(([^)]+)\)', r'\1.destination'),
        ]
    },
    {
        "file": "pages/AdminPage/EmployeeTravel.jsx",
        "import_pattern": r'import\s*{\s*formatLocationDisplay\s*}\s*from\s*[\'"]\.\.?/.*?locationFormatter[\'"];?\n?',
        "usage_patterns": [
            (r'formatLocationDisplay\(([^)]+)\)', r'\1.destination'),
        ]
    },
    {
        "file": "pages/AdminPage/EmployeeLiquidations.jsx",
        "import_pattern": r'import\s*{\s*formatLocationDisplay\s*}\s*from\s*[\'"]\.\.?/.*?locationFormatter[\'"];?\n?',
        "usage_patterns": [
            (r'formatLocationDisplay\(([^)]+\.travel_order)\)', r'\1?.destination'),
        ]
    },
    {
        "file": "pages/AdminPage/Reports.jsx",
        "import_pattern": r'import\s*{\s*formatLocationDisplay\s*}\s*from\s*[\'"]\.\.?/.*?locationFormatter[\'"];?\n?',
        "usage_patterns": [
            (r'formatLocationDisplay\(([^)]+)\)', r'\1.destination'),
            (r'formatLocationDisplay\(([^)]+\.travel_order)\)', r'\1?.destination'),
        ]
    },
    {
        "file": "components/NotificationDropdown.jsx",
        "import_pattern": r'import\s*{\s*formatLocationDisplay\s*}\s*from\s*[\'"]\.\.?/.*?locationFormatter[\'"];?\n?',
        "usage_patterns": [
            (r'formatLocationDisplay\(([^)]+\.travel_order)\)', r'\1?.destination'),
        ]
    },
    {
        "file": "pages/LiquidationApproval.jsx",
        "import_pattern": r'import\s*{\s*formatLocationDisplay\s*}\s*from\s*[\'"]\.\.?/.*?locationFormatter[\'"];?\n?',
        "usage_patterns": [
            (r'formatLocationDisplay\(([^)]+\.travel_order)\)', r'\1?.destination'),
        ]
    },
    {
        "file": "components/HeadApprovalPanel.jsx",
        "import_pattern": r'import\s*{\s*formatLocationDisplay\s*}\s*from\s*[\'"]\.\.?/.*?locationFormatter[\'"];?\n?',
        "usage_patterns": [
            (r'formatLocationDisplay\(([^)]+)\)', r'\1.destination'),
        ]
    },
    {
        "file": "pages/LiquidationList.jsx",
        "import_pattern": r'import\s*{\s*formatLocationDisplay\s*}\s*from\s*[\'"]\.\.?/.*?locationFormatter[\'"];?\n?',
        "usage_patterns": [
            (r'formatLocationDisplay\(([^)]+\.travel_order)\)', r'\1?.destination'),
        ]
    }
]

def fix_file(file_info):
    """Fix a single file"""
    file_path = os.path.join(base_dir, file_info["file"])
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remove import
        content = re.sub(
            file_info["import_pattern"],
            '// Removed locationFormatter - using direct destination field\n',
            content
        )
        
        # Apply usage patterns
        for pattern, replacement in file_info["usage_patterns"]:
            content = re.sub(pattern, replacement, content)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Fixed: {file_info['file']}")
        return True
        
    except Exception as e:
        print(f"❌ Error fixing {file_info['file']}: {e}")
        return False

def main():
    """Fix all files"""
    print("🔄 Fixing locationFormatter usage in React components...")
    
    success_count = 0
    for file_info in files_to_fix:
        if fix_file(file_info):
            success_count += 1
    
    print(f"\n📊 Results: {success_count}/{len(files_to_fix)} files fixed successfully")
    
    if success_count == len(files_to_fix):
        print("🎉 All components fixed successfully!")
    else:
        print("⚠️  Some files failed to fix. Check the errors above.")

if __name__ == "__main__":
    main()
