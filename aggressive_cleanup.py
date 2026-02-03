#!/usr/bin/env python3
"""
Aggressive cleanup script - keeps only the most recent itinerary per travel order
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

def aggressive_cleanup():
    """Keep only the most recent itinerary for each travel order"""
    
    print("🧹 Aggressive Itinerary Cleanup")
    print("=" * 50)
    print("This will keep only the MOST RECENT itinerary for each travel order.")
    print("All older itineraries will be deleted.")
    
    # Get all travel orders
    travel_orders = TravelOrder.objects.all()
    total_removed = 0
    
    for travel_order in travel_orders:
        # Get all itineraries for this travel order, ordered by ID (most recent last)
        itineraries = Itinerary.objects.filter(travel_order=travel_order).order_by('id')
        
        if itineraries.count() > 1:
            print(f"\n📋 Travel Order {travel_order.id}: {itineraries.count()} itineraries")
            
            # Keep only the last one (highest ID)
            keep_itinerary = itineraries.last()
            duplicates = itineraries.exclude(id=keep_itinerary.id)
            
            print(f"  Keeping: ID {keep_itinerary.id} (Date: {keep_itinerary.itinerary_date})")
            print(f"  Deleting: {duplicates.count()} older itineraries")
            
            # Show what we're deleting
            for dup in duplicates:
                print(f"    - ID {dup.id} (Date: {dup.itinerary_date}, Destination: {dup.destination})")
            
            # Delete the older ones
            deleted_count = duplicates.count()
            duplicates.delete()
            total_removed += deleted_count
            
            print(f"  ✅ Removed {deleted_count} duplicate itineraries")
    
    print(f"\n🎉 Cleanup Complete!")
    print(f"   Total itineraries removed: {total_removed}")
    
    # Show final stats
    print(f"\n📊 Final Statistics:")
    for travel_order in TravelOrder.objects.all():
        count = Itinerary.objects.filter(travel_order=travel_order).count()
        print(f"  Travel Order {travel_order.id}: {count} itineraries")

if __name__ == "__main__":
    aggressive_cleanup()

