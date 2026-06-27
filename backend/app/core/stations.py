"""
===========================================================================
 VAYU DRISHTI — SINGLE SOURCE OF TRUTH: Delhi CPCB Station Definitions
===========================================================================
 All 40 Delhi monitoring stations with precise GPS coordinates.
 
 This file is the ONLY place station definitions live.
 Every other module (training, inference, testing, dashboard) imports
 from here. Never duplicate this dictionary elsewhere.

 Last updated: 2026-06-15 — coordinates verified against CPCB/DPCC records.
===========================================================================
"""

# Precise GPS coordinates for each CPCB/DPCC monitoring station in Delhi.
# Format: "Station Name": (latitude, longitude)
STATION_COORDS = {
    "Alipur, Delhi - DPCC": (28.815329, 77.15301),
    "Anand Vihar, Delhi - DPCC": (28.646835, 77.316032),
    "Ashok Vihar, Delhi - DPCC": (28.695381, 77.181665),
    "Bawana, Delhi - DPCC": (28.7762, 77.051074),
    "Cantonment Area, Delhi - DPCC": (28.5913, 77.1355),
    "Chandni Chowk, Delhi - IITM": (28.656756, 77.227234),
    "Commonwealth Sports Complex, Delhi - DPCC": (28.6136, 77.2758),
    "DTU, Delhi - CPCB": (28.75005, 77.1112615),
    "Dr. Karni Singh Shooting Range, Delhi - DPCC": (28.498571, 77.26484),
    "Dwarka-Sector 8, Delhi - DPCC": (28.5710274, 77.0719006),
    "IGNOU_Maidan Garhi, Delhi - DPCC": (28.4975, 77.2026),
    "IHBAS, Dilshad Garden, Delhi - CPCB": (28.6821, 77.305),
    "IIT Delhi, Delhi - IITM": (28.5448, 77.1923),
   # "IMD Lodhi Road": (28.588, 77.2215),# This station has no data


    "ITO, Delhi - CPCB": (28.628624, 77.24106),
    "JNU, Delhi - DPCC": (28.5398, 77.1654),
    "Jahangirpuri, Delhi - DPCC": (28.73282, 77.170633),
    "Jawaharlal Nehru Stadium, Delhi - DPCC": (28.58028, 77.233829),
    "Lodhi Road, Delhi - IITM": (28.588333, 77.221667),
    "Major Dhyan Chand National Stadium, Delhi - DPCC": (28.611281, 77.237738),
    "Mandir Marg, Delhi - DPCC": (28.6341, 77.2005),
    "Mundka, Delhi - DPCC": (28.684678, 77.076574),
    "NSIT Dwarka, Delhi - CPCB": (28.60909, 77.0325413),
    "NSUT Jaffarpur, Delhi - DPCC": (28.6041, 76.9029),
    "Najafgarh, Delhi - DPCC": (28.570173, 76.933762),
    "Narela, Delhi - DPCC": (28.822836, 77.101981),
    "Nehru Nagar, Delhi - DPCC": (28.56789, 77.250515),
    "Okhla Phase-2, Delhi - DPCC": (28.530785, 77.271255),
    "Patparganj, Delhi - DPCC": (28.623748, 77.287205),
    "Punjabi Bagh, Delhi - DPCC": (28.674045, 77.131023),
    "Pusa, Delhi - DPCC": (28.639645, 77.146262),
    "R K Puram, Delhi - DPCC": (28.563262, 77.186937),
    "Rohini, Delhi - DPCC": (28.732528, 77.11992),
    "Shadipur, Delhi - CPCB": (28.6514781, 77.1473105),
    "Sirifort, Delhi - CPCB": (28.5504249, 77.2159377),
    "Sonia Vihar, Delhi - DPCC": (28.710508, 77.249485),
    "Sri Aurobindo Marg, Delhi - DPCC": (28.531346, 77.190156),
    "Talkatora Garden, Delhi - DPCC": (28.6247, 77.1979),
    "Vivek Vihar, Delhi - DPCC": (28.672342, 77.31526),
    "Wazirpur, Delhi - DPCC": (28.699793, 77.165453)
}

# Geographic center of Delhi — used for dist_center feature calculation
DELHI_CENTER = (28.6139, 77.2090)

# Total station count (for validation assertions)
TOTAL_STATIONS = len(STATION_COORDS)
assert TOTAL_STATIONS == 39, f"Expected 39 stations, got {TOTAL_STATIONS}"
