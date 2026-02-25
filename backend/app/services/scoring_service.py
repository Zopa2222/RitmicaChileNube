def calculate_total_score(gymnast, judges):
    """
    Calculate total score for a gymnast based on FIG rules
    
    Args:
        gymnast: dict with DA, DB, E (array), A (array), Desc
        judges: list of judge dicts with 'rol' field
    
    Returns:
        float: total score
    """
    total = 0.0
    
    # Add DA and DB directly
    total += gymnast.get('DA', 0.0)
    total += gymnast.get('DB', 0.0)
    
    # Calculate E score
    e_scores = gymnast.get('E', [])
    if e_scores:
        e_deduction = calculate_area_deduction(e_scores)
        total += (10 - e_deduction)
    
    # Calculate A score
    a_scores = gymnast.get('A', [])
    if a_scores:
        a_deduction = calculate_area_deduction(a_scores)
        total += (10 - a_deduction)
    
    # Subtract Desc
    total -= gymnast.get('Desc', 0.0)
    
    return max(0.0, round(total, 2))


def calculate_area_deduction(scores):
    """
    Calculate deduction for E or A area
    
    Rules:
    - 1 judge: use that score
    - 2-3 judges: average all scores
    - 4+ judges: average excluding min and max
    
    Args:
        scores: list of floats
    
    Returns:
        float: deduction value
    """
    if not scores:
        return 0.0
    
    count = len(scores)
    
    if count == 1:
        return scores[0]
    elif count in [2, 3]:
        return sum(scores) / count
    else:  # 4 or more
        sorted_scores = sorted(scores)
        # Exclude min and max
        middle_scores = sorted_scores[1:-1]
        return sum(middle_scores) / len(middle_scores)


def calculate_e_score(gymnast):
    """
    Calculate E score for a gymnast (for tiebreaker purposes)
    
    Args:
        gymnast: dict with E array
    
    Returns:
        float: the E score (10 - deduction)
    """
    e_scores = gymnast.get('E', [])
    if e_scores:
        e_deduction = calculate_area_deduction(e_scores)
        return 10 - e_deduction
    return 0.0


def validate_scores(gymnast):
    """
    Validate scores and check for differences > 0.6 in E and A areas
    
    Args:
        gymnast: dict with E and A arrays
    
    Returns:
        dict: { 'has_error': bool, 'error_areas': list }
    """
    error_areas = []
    
    # Check E scores
    e_scores = gymnast.get('E', [])
    if len(e_scores) >= 2:
        if max(e_scores) - min(e_scores) > 0.6:
            error_areas.append('E')
    
    # Check A scores
    a_scores = gymnast.get('A', [])
    if len(a_scores) >= 2:
        if max(a_scores) - min(a_scores) > 0.6:
            error_areas.append('A')
    
    return {
        'has_error': len(error_areas) > 0,
        'error_areas': error_areas
    }
