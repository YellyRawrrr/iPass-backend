#!/usr/bin/env python3
"""
Script to update all React components to use direct destination field
instead of locationFormatter
"""

import os
import re

# Files to update
files_to_update = [
    "trialreact/src/pages/Bookkeeper/BookkeeperReview.jsx",
    "trialreact/src/components/TravelOrderPDF.jsx", 
    "trialreact/src/pages/Heads/HeadApprovalDetails.jsx",
    "trialreact/src/pages/Employee/EmployeeLiquidation.jsx",
    "trialreact/src/components/TravelOrderFormSteps/ValidationStep.jsx",
    "trialreact/src/pages/Accountant/AccountantReview.jsx",
    "trialreact/src/components/ViewApproval.jsx",
    "trialreact/src/pages/Employee/MyTravels.jsx",
    "trialreact/src/pages/AdminPage/EmployeeTravel.jsx",
    "trialreact/src/pages/AdminPage/EmployeeLiquidations.jsx",
    "trialreact/src/pages/AdminPage/Reports.jsx",
    "trialreact/src/components/NotificationDropdown.jsx",
    "trialreact/src/pages/LiquidationApproval.jsx",
    "trialreact/src/components/HeadApprovalPanel.jsx",
    "trialreact/src/pages/LiquidationList.jsx"
]

def update_file(file_path):
    """Update a single file to remove locationFormatter usage"""
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remove import statement
        content = re.sub(
            r'import\s*{\s*formatLocationDisplay\s*}\s*from\s*[\'"]\.\.?/.*?locationFormatter[\'"];?\n?',
            '// Removed locationFormatter - using direct destination field\n',
            content
        )
        
        # Replace formatLocationDisplay calls with direct destination access
        # Pattern 1: formatLocationDisplay(data.travel_order) -> data.travel_order?.destination
        content = re.sub(
            r'formatLocationDisplay\(([^)]+\.travel_order)\)',
            r'\1?.destination',
            content
        )
        
        # Pattern 2: formatLocationDisplay(order) -> order.destination  
        content = re.sub(
            r'formatLocationDisplay\(([^)]+)\)',
            r'\1.destination',
            content
        )
        
        # Pattern 3: formatLocationDisplay(item.travel_order || item) -> (item.travel_order || item)?.destination
        content = re.sub(
            r'formatLocationDisplay\(([^)]+\|\|[^)]+)\)',
            r'(\1)?.destination',
            content
        )
        
        # Pattern 4: formatLocationDisplay(liquidation.travel_order) -> liquidation.travel_order?.destination
        content = re.sub(
            r'formatLocationDisplay\(([^)]+\.travel_order)\)',
            r'\1?.destination',
            content
        )
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Updated: {file_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error updating {file_path}: {e}")
        return False

def main():
    """Update all files"""
    print("🔄 Updating React components to use direct destination field...")
    
    success_count = 0
    for file_path in files_to_update:
        if update_file(file_path):
            success_count += 1
    
    print(f"\n📊 Results: {success_count}/{len(files_to_update)} files updated successfully")
    
    if success_count == len(files_to_update):
        print("🎉 All components updated successfully!")
    else:
        print("⚠️  Some files failed to update. Check the errors above.")

if __name__ == "__main__":
    main()
