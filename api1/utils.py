# utils.py
# Utility functions for travel order management and approval workflow
from .models import CustomUser, EMPLOYEE_TYPE_CHOICES, TravelOrder
from datetime import datetime

def build_status_map():
    """Build status message mapping for different employee types"""
    base_map = {}
    for code, label in EMPLOYEE_TYPE_CHOICES:
        if code == 'regional':
            base_map[code] = {
                'approve': 'The travel order has been approved by the Regional Director',
                'reject': 'The travel order has been rejected by the Regional Director',
            }
        elif code == 'tmsd':
            base_map[code] = {
                'approve': f'The travel order has been approved by the {label} chief',
                'reject': f'The travel order has been rejected by the {label} chief',
            }
        elif code == 'afsd':
            base_map[code] = {
                'approve': f'The travel order has been approved by the {label} Chief',
                'reject': f'The travel order has been rejected by the {label} Chief',
            }
        else:
            base_map[code] = {
                'approve': f'The travel order has been approved by the {label} head',
                'reject': f'The travel order has been rejected by the {label} head',
            }
    return base_map

APPROVAL_CHAIN_MAP = {
    'urdaneta_csc': ['urdaneta_csc', 'pangasinan_po', 'tmsd', 'afsd', 'regional'],
    'sison_csc': ['sison_csc', 'pangasinan_po', 'tmsd', 'afsd', 'regional'],
    'pugo_csc': ['pugo_csc', 'launion_po', 'tmsd', 'afsd', 'regional'],
    'sudipen_csc': ['sudipen_csc', 'launion_po', 'tmsd', 'afsd', 'regional'],
    'tagudin_csc': ['tagudin_csc', 'ilocossur_po', 'tmsd', 'afsd', 'regional'],
    'banayoyo_csc': ['banayoyo_csc', 'ilocossur_po', 'tmsd', 'afsd', 'regional'],
    'dingras_csc': ['dingras_csc', 'ilocosnorte_po', 'tmsd', 'afsd', 'regional'],

    'pangasinan_po': ['pangasinan_po', 'tmsd', 'afsd', 'regional'],
    'ilocossur_po': ['ilocossur_po', 'tmsd', 'afsd', 'regional'],
    'ilocosnorte_po': ['ilocosnorte_po', 'tmsd', 'afsd', 'regional'],
    'launion_po': ['launion_po', 'tmsd', 'afsd', 'regional'],

    'tmsd': ['tmsd','afsd', 'regional'],
    'afsd': ['afsd', 'regional'],
    'regional': [],
}

def get_approval_chain(user):
    """
    Returns the hierarchical approval chain based on the user's role and type.
    """

    if user.user_level == 'director':
        # Director cannot file travel orders
        return []

    # CSC Employee
    if user.employee_type == 'urdaneta_csc':
        if user.user_level == 'head':
            return ['pangasinan_po', 'tmsd', 'afsd', 'regional']
        else:
            return ['urdaneta_csc', 'pangasinan_po', 'tmsd', 'afsd', 'regional']
        
    if user.employee_type == 'sison_csc':
        if user.user_level == 'head':
            return ['pangasinan_po', 'tmsd', 'afsd', 'regional']
        else:
            return ['sison_csc', 'pangasinan_po', 'tmsd', 'afsd', 'regional']

    if user.employee_type == 'pugo_csc':
        if user.user_level == 'head':
            return ['launion_po', 'tmsd', 'afsd', 'regional']
        else:
            return ['pugo_csc', 'launion_po', 'tmsd', 'afsd', 'regional']

    if user.employee_type == 'sudipen_csc':
        if user.user_level == 'head':
            return ['launion_po', 'tmsd', 'afsd', 'regional']
        else:
            return ['sudipen_csc', 'launion_po', 'tmsd', 'afsd', 'regional']
                            
    if user.employee_type == 'tagudin_csc':
        if user.user_level == 'head':
            return ['ilocossur_po', 'tmsd', 'afsd', 'regional']
        else:
            return ['tagudin_csc', 'ilocossur_po', 'tmsd', 'afsd', 'regional']

    if user.employee_type == 'banayoyo_csc':
        if user.user_level == 'head':
            return ['ilocossur_po', 'tmsd', 'afsd', 'regional']
        else:
            return ['banayoyo_csc', 'ilocossur_po', 'tmsd', 'afsd', 'regional']
        
    if user.employee_type == 'dingras_csc':
        if user.user_level == 'head':
            return ['ilocosnorte_po', 'tmsd', 'afsd', 'regional']
        else:
            return ['dingras_csc', 'ilocosnorte_po', 'tmsd', 'afsd', 'regional']                        

    # PO Employee
    if user.employee_type == 'pangasinan_po':
        if user.user_level == 'head':
            return ['tmsd', 'afsd', 'regional']
        else:
            return ['pangasinan_po', 'tmsd', 'afsd', 'regional']
        
    if user.employee_type == 'ilocossur_po':
        if user.user_level == 'head':
            return ['tmsd', 'afsd', 'regional']
        else:
            return ['ilocossur_po', 'tmsd', 'afsd', 'regional']

    if user.employee_type == 'ilocosnorte_po':
        if user.user_level == 'head':
            return ['tmsd', 'afsd', 'regional']
        else:
            return ['ilocosnorte_po', 'tmsd', 'afsd', 'regional']

    if user.employee_type == 'launion_po':
        if user.user_level == 'head':
            return ['tmsd', 'afsd', 'regional']
        else:
            return ['launion_po', 'tmsd', 'afsd', 'regional']                        

    # TMSD Employee
    if user.employee_type == 'tmsd':
        if user.user_level == 'head':
            return ['afsd', 'regional']
        else:
            return ['tmsd', 'afsd', 'regional']

    # AFSD Employee
    if user.employee_type == 'afsd':
        return ['afsd', 'regional']

    # Regional Employee (non-director)
    if user.employee_type == 'regional':
        return ['regional']

    # Fallback
    return []


def get_next_head(chain, stage, current_user=None):
    """
    Returns the next head approver based on the approval chain and current stage.
    Ensures the same user doesn't approve twice.
    """
    while stage < len(chain):
        next_type = chain[stage]

        # Strictly get the head for the next stage
        qs = CustomUser.objects.filter(employee_type=next_type, user_level='head')

        # Avoid returning the same person again
        if current_user:
            qs = qs.exclude(id=current_user.id)

        next_head = qs.first()
        if next_head:
            return next_head

        # Skip to next stage if no head found
        stage += 1

    # Final fallback: Director (if not same as current)
    qs = CustomUser.objects.filter(user_level='director')
    if current_user:
        qs = qs.exclude(id=current_user.id)

    return qs.first()





def generate_travel_order_number(original_number=None):
    """
    Generate a unique travel order number in the format: R1-YYYY-MM-XXXX
    where YYYY is the current year, MM is the current month, and XXXX is a sequential number.
    
    If original_number is provided (for amendments), returns: Amending-{original_number}
    """
    # If this is an amendment, return the amended format
    if original_number:
        return f'Amending-{original_number}'
    
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    
    # Get the last travel order number for this year and month
    prefix = f"R1-{current_year}-{current_month:02d}-"
    last_order = TravelOrder.objects.filter(
        travel_order_number__startswith=prefix
    ).order_by('-travel_order_number').first()
    
    if last_order:
        # Extract the number part and increment
        try:
            last_number = int(last_order.travel_order_number.split('-')[-1])
            next_number = last_number + 1
        except (ValueError, IndexError):
            next_number = 1
    else:
        next_number = 1
    
    return f'{prefix}{next_number:04d}'