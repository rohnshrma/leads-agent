"""
Niche -> OpenStreetMap tag mapping.

OSM has no free-text business search, so each niche must be expressed as
real OSM tags. These are the tags US businesses are actually mapped under.

Honest coverage note: OSM is good for businesses with PREMISES (a dentist,
a gym, a driving school, an auto shop) and weak for service-area trades
(roofers, plumbers) who have no storefront to map. The default niche list
in config.yaml leans towards the former for exactly this reason.
"""

NICHE_TAGS: dict[str, list[str]] = {
    "driving school":       ['amenity="driving_school"'],
    "auto repair shop":     ['shop="car_repair"'],
    "car dealership":       ['shop="car"'],
    "tyre shop":            ['shop="tyres"'],
    "dental clinic":        ['amenity="dentist"', 'healthcare="dentist"'],
    "doctor clinic":        ['amenity="doctors"', 'healthcare="doctor"'],
    # Most chiropractors are mapped as healthcare=alternative with a chiropractic speciality;
    # healthcare=chiropractor alone found 0 in every Canadian city.
    "chiropractor":         ['"healthcare:speciality"~"chiropract"', 'healthcare="chiropractor"',
                             'healthcare][name~"chiropract",i', 'amenity="clinic"][name~"chiropract",i'],
    "physiotherapist":      ['healthcare="physiotherapist"'],
    "veterinary clinic":    ['amenity="veterinary"'],
    "optician":             ['shop="optician"'],
    "optometrist":          ['healthcare="optometrist"', 'shop="optician"'],
    "orthodontist":         ['"healthcare:speciality"~"orthodont"', 'amenity="dentist"][name~"orthodont",i'],
    "dermatology clinic":   ['"healthcare:speciality"~"dermatolog"', 'amenity="clinic"][name~"derm|skin|laser|cosmetic|aesthetic",i'],
    "hearing clinic":       ['healthcare="audiologist"', 'shop="hearing_aids"'],
    "psychology clinic":    ['healthcare="psychotherapist"', 'healthcare="psychologist"',
                             '"healthcare:speciality"~"psycholog|psychotherap"',
                             'healthcare][name~"psycholog|counsell?ing",i'],
    "podiatrist":           ['healthcare="podiatrist"'],
    "massage therapy clinic": ['healthcare="massage"', 'shop="massage"'],
    "pharmacy":             ['amenity="pharmacy"'],
    "law firm":             ['office="lawyer"'],
    "accounting firm":      ['office="accountant"'],
    "insurance agency":     ['office="insurance"'],
    "real estate agency":   ['office="estate_agent"'],
    "financial advisor":    ['office="financial_advisor"'],
    "gym fitness studio":   ['leisure="fitness_centre"'],
    "yoga studio":          ['leisure="fitness_centre"', 'sport="yoga"'],
    "daycare preschool":    ['amenity="kindergarten"', 'amenity="childcare"'],
    "hair salon":           ['shop="hairdresser"'],
    "nail salon":           ['shop="beauty"'],
    # Plain shop=beauty is mostly nail and lash bars; keep the ones that read like a medical spa.
    "med spa":              ['shop="beauty"][name~"med ?spa|medi|aesthetic|laser|cosmetic|clinic|botox|injectab",i', 'healthcare="spa"'],
    "tattoo studio":        ['shop="tattoo"'],
    "funeral home":         ['shop="funeral_directors"'],
    "self storage":         ['shop="storage_rental"'],
    "pet grooming":         ['shop="pet_grooming"'],
    "restaurant":           ['amenity="restaurant"'],
    "cafe":                 ['amenity="cafe"'],
    "bakery":               ['shop="bakery"'],
    "florist":              ['shop="florist"'],
    "jewellery store":      ['shop="jewelry"'],
    "furniture store":      ['shop="furniture"'],
    "hardware store":       ['shop="hardware"', 'shop="doityourself"'],
    "garden centre":        ['shop="garden_centre"'],
    "dry cleaner":          ['shop="dry_cleaning"', 'shop="laundry"'],
    "printing shop":        ['shop="copyshop"'],
    "travel agency":        ['shop="travel_agency"'],
    # Service-area trades - present in OSM but sparsely. Kept for when you
    # switch to Overture, which covers them far better.
    "plumber":              ['craft="plumber"'],
    "electrician":          ['craft="electrician"'],
    "roofing contractor":   ['craft="roofer"'],
    "HVAC contractor":      ['craft="hvac"'],
    "carpenter":            ['craft="carpenter"'],
    "painter":              ['craft="painter"'],
    "landscaping company":  ['craft="gardener"'],
    "pest control":         ['craft="pest_control"'],
    "locksmith":            ['craft="locksmith"'],
}


def tags_for(niche: str) -> list[str]:
    n = niche.strip().lower()
    if n in NICHE_TAGS:
        return NICHE_TAGS[n]
    # Fall back to a name search so an unmapped niche still returns something.
    safe = niche.replace('"', "").replace("\\", "")
    return [f'name~"{safe}",i']


def known_niches() -> list[str]:
    return sorted(NICHE_TAGS)
