#!/usr/bin/env python3
"""
Automatic cleanup script for duplicate itineraries
"""

import os
import sys
import django

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project1.settings')
django.setup()

from api1.models import TravelOrder, Itinerary
from collections import defaultdict

def cleanup_duplicate_itineraries():
    """Clean up duplicate itineraries by keeping only the most recent ones"""
    
    print("🔍 Scanning for travel orders with duplicate itineraries...")
    
    # Get all travel orders
    travel_orders = TravelOrder.objects.all()
    cleaned_count = 0
    total_duplicates = 0
    
    for travel_order in travel_orders:
        # Get all itineraries for this travel order
        itineraries = Itinerary.objects.filter(travel_order=travel_order).order_by('id')
        
        if itineraries.count() > 1:
            print(f"\n📋 Travel Order {travel_order.id} has {itineraries.count()} itineraries:")
            
            # Group itineraries by their content (excluding ID and travel_order)
            itinerary_groups = defaultdict(list)
            
            for itinerary in itineraries:
                # Create a key based on the itinerary content
                key = (
                    itinerary.itinerary_date,
                    itinerary.departure_time,
                    itinerary.arrival_time,
                    itinerary.destination,
                    float(itinerary.transportation_allowance),
                    float(itinerary.per_diem),
                    float(itinerary.other_expense),
                    float(itinerary.total_amount),
                    itinerary.transportation_id if itinerary.transportation else None
                )
                itinerary_groups[key].append(itinerary)
            
            # For each group, keep only the most recent itinerary (highest ID)
            for key, group in itinerary_groups.items():
                if len(group) > 1:
                    print(f"  Found {len(group)} duplicate itineraries for date {group[0].itinerary_date}")
                    
                    # Sort by ID and keep the last one
                    group.sort(key=lambda x: x.id)
                    keep_itinerary = group[-1]
                    duplicates = group[:-1]
                    
                    print(f"    Keeping itinerary ID {keep_itinerary.id}")
                    print(f"    Deleting {len(duplicates)} duplicates: {[d.id for d in duplicates]}")
                    
                    # Delete the duplicates
                    for duplicate in duplicates:
                        duplicate.delete()
                        total_duplicates += 1
                    
                    cleaned_count += 1
    
    print(f"\n✅ Cleanup complete!")
    print(f"   - Travel orders cleaned: {cleaned_count}")
    print(f"   - Duplicate itineraries removed: {total_duplicates}")

if __name__ == "__main__":
    print("🧹 Automatic Itinerary Cleanup")
    print("=" * 50)
    cleanup_duplicate_itineraries()

