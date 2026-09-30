"""
Niche content + design tokens for the mockup generator.

Every string may use:
  {city} {state} {city_state} {name} {phone}   - filled from the lead
  [[text]]                                     - rendered as a dashed
                                                 "add yours" placeholder

HONESTY RULE: a mockup only knows the business's name, address, phone,
email, niche and map position. Anything else (reviews, years in business,
credentials, prices, staff, pass rates, certifications, hours) must be
either generic process copy the owner can confirm, or a visible [[placeholder]].
Never invent facts the business could be held to.

Palettes come in two variants (A/B, from the design research); a lead gets
one of them deterministically so consecutive mockups don't all look alike.
Roles:  bg surface ink muted primary on_primary accent on_accent tint line
"""

from __future__ import annotations

# ---------------------------------------------------------------- fonts
# family -> [(weight, file)]  (files live in mockups/static/fonts)
FONTS = {
    "Poppins": [(600, "poppins-latin-600-normal.woff2"), (700, "poppins-latin-700-normal.woff2"), (800, "poppins-latin-800-normal.woff2")],
    "Inter": [(400, "inter-latin-400-normal.woff2"), (500, "inter-latin-500-normal.woff2"), (600, "inter-latin-600-normal.woff2"), (700, "inter-latin-700-normal.woff2")],
    "Barlow Condensed": [(600, "barlow-condensed-latin-600-normal.woff2"), (700, "barlow-condensed-latin-700-normal.woff2"), (800, "barlow-condensed-latin-800-normal.woff2")],
    "Plus Jakarta Sans": [(400, "plus-jakarta-sans-latin-400-normal.woff2"), (500, "plus-jakarta-sans-latin-500-normal.woff2"), (600, "plus-jakarta-sans-latin-600-normal.woff2"), (700, "plus-jakarta-sans-latin-700-normal.woff2"), (800, "plus-jakarta-sans-latin-800-normal.woff2")],
    "Anton": [(400, "anton-latin-400-normal.woff2")],
    "Manrope": [(400, "manrope-latin-400-normal.woff2"), (500, "manrope-latin-500-normal.woff2"), (600, "manrope-latin-600-normal.woff2"), (700, "manrope-latin-700-normal.woff2"), (800, "manrope-latin-800-normal.woff2")],
    "Playfair Display": [(600, "playfair-display-latin-600-normal.woff2"), (700, "playfair-display-latin-700-normal.woff2")],
    "Source Sans 3": [(400, "source-sans-3-latin-400-normal.woff2"), (600, "source-sans-3-latin-600-normal.woff2"), (700, "source-sans-3-latin-700-normal.woff2")],
    "Lora": [(500, "lora-latin-500-normal.woff2"), (600, "lora-latin-600-normal.woff2"), (700, "lora-latin-700-normal.woff2")],
}

# ------------------------------------------------------------- niches
NICHES: dict[str, dict] = {}

NICHES["driving_school"] = {
    "label": "Driving school",
    "keywords": ["driving school", "driving_school", "driver education", "driver's ed", "drivers ed"],
    "template": "driving_school.html.j2",
    "fonts": ["Poppins", "Inter"],
    "heading_font": "Poppins", "body_font": "Inter",
    "palettes": [
        dict(name="Road Sign", bg="#F7F8FA", surface="#FFFFFF", ink="#0F2A4A", muted="#475569",
             primary="#0F2A4A", on_primary="#FFFFFF", accent="#FFC72C", on_accent="#0F2A4A",
             tint="#EAF0F8", line="#D9E1EC"),
        dict(name="Fresh Start", bg="#FFF8F0", surface="#FFFFFF", ink="#1F2937", muted="#566274",
             primary="#0E7C7B", on_primary="#FFFFFF", accent="#FF6B4A", on_accent="#1F2937",
             tint="#E3F6EE", line="#EADFD2"),
    ],
    "h1": "Learn to drive with confidence in {city_state}",
    "sub": "Driver's ed and private lessons for teens and adults.",
    "chips": ["Teens & adults", "One-on-one lessons", "Serving {city}"],
    "cta_primary": "Book a lesson",
    "cta_secondary": "Call {phone}",
    "services_title": "Lessons and programs",
    "services": [
        ("wheel", "Teen Driver's Ed", "Classroom plus behind-the-wheel hours toward your license."),
        ("user", "Adult Driving Lessons", "Flexible lessons for first-time or returning adult drivers."),
        ("route", "Road Test Preparation", "Practice the exact skills examiners check."),
        ("car", "Behind-the-Wheel Training", "One-on-one instruction in a training vehicle."),
        ("shield", "Defensive Driving Course", "Hazard awareness that can help with insurance or ticket points."),
        ("road", "Highway & Freeway Driving", "Merging, lane changes and speed confidence."),
        ("parking", "Parallel Parking & Maneuvers", "Parking, three-point turns and backing."),
        ("refresh", "Refresher Lessons", "Rebuild confidence after time off the road."),
    ],
    "steps_title": "From permit to license",
    "steps": [
        ("Get your permit", "Pass the written test and get your learner's permit. [[Add your state's requirements]]"),
        ("Start your lessons", "Book behind-the-wheel sessions that fit your schedule."),
        ("Prepare for the road test", "Practice the maneuvers examiners look for, in a familiar setting."),
        ("Get licensed", "Take your road test with confidence and start driving."),
    ],
    "extras": {
        "packages_title": "Lesson packages",
        "packages": [
            ("Starter", "[[2 hours]]", "A first look behind the wheel.", False),
            ("Standard", "[[6 hours]]", "Build real skills and comfort.", True),
            ("Road-Test Ready", "[[10 hours]]", "Everything you need before your test.", False),
        ],
        "why_title": "Why learn with us",
        "why": [
            ("user", "One-on-one attention", "Your instructor focuses on you, at your pace. [[Confirm]]"),
            ("pin", "Pickup options", "Pickup from home, school or work within [[your service area]]."),
            ("heart", "Patient, calm teaching", "No shouting, no pressure. Just clear steps."),
        ],
        "checklist_title": "What to bring to your road test",
        "checklist": [
            "Your learner's permit",
            "Proof of insurance and registration, if you use your own car",
            "Glasses or contacts, if you wear them",
            "Your appointment confirmation",
            "A licensed adult, if your state requires one",
        ],
    },
    "faq": [
        ("Do I need a permit before my first lesson?", "Most states require a learner's permit before behind-the-wheel practice. Rules vary, so [[confirm your school's policy]]."),
        ("How many lessons will I need to pass?", "It depends on your experience and comfort behind the wheel. We suggest a plan after your first lesson. [[Add your typical range]]"),
        ("Can I use your car for the road test?", "[[Yes or no - add your policy]]. Many schools offer this as an add-on."),
        ("Are lessons one-on-one, and do you offer pickup?", "[[Confirm]]. Pickup can be arranged within [[your service area]]."),
        ("What is the minimum age to start driver's ed?", "Age rules are set by your state's DMV. [[Add the minimum age for your state]]."),
    ],
    "disclaimer": "",
}

NICHES["auto_repair"] = {
    "label": "Auto repair shop",
    "keywords": ["auto repair", "car_repair", "car repair", "mechanic", "tire", "tyre", "garage"],
    "template": "auto_repair.html.j2",
    "fonts": ["Barlow Condensed", "Inter"],
    "heading_font": "Barlow Condensed", "body_font": "Inter",
    "palettes": [
        dict(name="Garage Dark", bg="#F4F5F7", surface="#FFFFFF", ink="#1C1F24", muted="#525B66",
             primary="#1C1F24", on_primary="#FFFFFF", accent="#D92D20", on_accent="#FFFFFF",
             tint="#E9ECF0", line="#D5DAE0"),
        dict(name="Trust Blue", bg="#EEF1F5", surface="#FFFFFF", ink="#2B2F36", muted="#4F5865",
             primary="#0B3D91", on_primary="#FFFFFF", accent="#FF7A00", on_accent="#1B1B1B",
             tint="#E1E8F2", line="#D2DAE6"),
    ],
    "h1": "Honest auto repair in {city_state}",
    "sub": "Brakes, diagnostics, oil changes and more. Straight answers before any work begins.",
    "chips": ["All makes & models", "Upfront estimates", "Local shop"],
    "cta_primary": "Request an appointment",
    "cta_secondary": "Call {phone}",
    "services_title": "What we fix",
    "services": [
        ("brake", "Brake Repair", "Pads, rotors, calipers and brake fluid."),
        ("gauge", "Check Engine & Diagnostics", "Computer scan and root-cause diagnosis."),
        ("oil", "Oil Change & Maintenance", "Oil, filters, fluids and scheduled service."),
        ("tire", "Tires & Alignment", "Rotation, balancing and alignment."),
        ("engine", "Engine Repair", "From minor leaks to major repairs."),
        ("snow", "A/C & Heating", "A/C recharge, heater and blower repair."),
        ("spring", "Suspension & Steering", "Shocks, struts and tie rods."),
        ("battery", "Battery & Electrical", "Testing, replacement, charging system and starters."),
    ],
    "steps_title": "How it works",
    "steps": [
        ("Call or book", "Tell us what your car is doing. [[Add booking method]]"),
        ("We diagnose", "We find the cause before recommending any work."),
        ("You approve the estimate", "We explain the problem and the price before we start."),
        ("Drive away", "Pick up your car with the work explained. [[Add your warranty terms]]"),
    ],
    "extras": {
        "why_title": "Why drivers choose a local shop",
        "why": [
            ("shield", "Upfront estimates", "We explain the problem and the price before we start. [[Confirm]]"),
            ("wrench", "Clear communication", "Plain-English explanations, no pressure."),
            ("car", "All makes and models", "Domestic, Asian and European vehicles. [[Confirm makes you service]]"),
        ],
        "makes": "Domestic · Asian · European",
        "reminder": "Oil change every 5,000 to 7,500 miles is a common guideline. Check your owner's manual for your car.",
        "special_placeholder": "[[Your current special]]",
        "financing_placeholder": "[[Financing available? Add details]]",
        "badges_placeholder": "[[ASE or AAA badge - add if applicable]]",
    },
    "faq": [
        ("Do you give estimates before starting work?", "Yes, we explain the problem and the price before any work begins. [[Confirm your policy]]"),
        ("Do you work on my make and model?", "We service many domestic, Asian and European vehicles. [[Confirm the makes you service]]"),
        ("Is there a warranty on repairs?", "[[Add your warranty terms]]"),
        ("How long will my repair take? Can I wait?", "It depends on the job. [[Add drop-off and waiting-area info]]"),
        ("Do I need an appointment, or do you take walk-ins?", "[[Add your appointment and walk-in policy]]"),
    ],
    "disclaimer": "",
}

NICHES["dental"] = {
    "label": "Dental clinic",
    "keywords": ["dental", "dentist", "orthodont"],
    "template": "dental.html.j2",
    "fonts": ["Plus Jakarta Sans"],
    "heading_font": "Plus Jakarta Sans", "body_font": "Plus Jakarta Sans",
    "palettes": [
        dict(name="Clinical Calm", bg="#F9FAFB", surface="#FFFFFF", ink="#0B3C49", muted="#47606A",
             primary="#0E7C86", on_primary="#FFFFFF", accent="#F4A261", on_accent="#0B3C49",
             tint="#E6F4F1", line="#D5E6E3"),
        dict(name="Warm Boutique", bg="#FBF8F3", surface="#FFFFFF", ink="#2F4858", muted="#55697A",
             primary="#2F4858", on_primary="#FFFFFF", accent="#E8916B", on_accent="#2B1A12",
             tint="#F3EDE4", line="#E6DDD0"),
    ],
    "h1": "Gentle, modern dental care in {city_state}",
    "sub": "New patients welcome. Call or request a visit online.",
    "chips": ["New patients welcome", "Family friendly", "Serving {city}"],
    "cta_primary": "Request an appointment",
    "cta_secondary": "Call {phone}",
    "services_title": "Dental care for the whole family",
    "services": [
        ("tooth", "General & Preventive", "Exams, cleanings and X-rays."),
        ("sparkle", "Cosmetic Dentistry", "Whitening, veneers and smile makeovers."),
        ("shield", "Restorative Care", "Fillings, crowns and bridges."),
        ("implant", "Dental Implants", "A long-term option for replacing teeth."),
        ("aligner", "Clear Aligners", "Orthodontic options such as clear aligners."),
        ("alert", "Emergency Dental Care", "Toothaches and broken teeth. Call us."),
        ("smile", "Family & Children", "Care for all ages."),
        ("roots", "Root Canal Therapy", "Saving teeth affected by infection."),
    ],
    "steps_title": "Your first visit",
    "steps": [
        ("Call or request a visit", "Tell us what you need and when works for you."),
        ("Exam and cleaning", "We take time to listen and look after the basics. [[Add what your first visit includes]]"),
        ("A clear plan", "We explain your options in plain language, with no pressure."),
    ],
    "extras": {
        "insurance": "We work with many PPO plans. Call to verify your coverage.",
        "insurance_tags": ["[[Insurance plans accepted]]", "[[Payment plans]]", "[[HSA / FSA]]"],
        "emergency": "Tooth pain? Call {phone}",
        "emergency_sub": "Tell us what is going on and we will do our best to help. [[Add your emergency policy]]",
        "offer_placeholder": "[[Your new-patient offer]]",
        "team_placeholder": "[[Meet the dentist - add photo and bio]]",
        "reviews_placeholder": "[[Your Google reviews appear here]]",
        "hours_placeholder": "[[Add your hours]]",
    },
    "faq": [
        ("Are you accepting new patients?", "Yes, new patients are welcome. [[Confirm]]"),
        ("Do you take my insurance? What are the payment options?", "We work with many PPO plans. Call to verify your coverage. [[Add payment options]]"),
        ("Do you handle dental emergencies?", "If you are in pain, call us and we will do our best to see you quickly. [[Add your policy]]"),
        ("What happens at my first visit and how long does it take?", "Your first visit usually includes an exam and a conversation about your goals. [[Add typical length]]"),
        ("Do you see children?", "[[Confirm whether you see children and from what age]]"),
    ],
    "disclaimer": "Sample design preview. Copy is generic and must be reviewed by the practice before publishing, "
                  "including compliance with your state dental board's advertising rules.",
}

NICHES["gym"] = {
    "label": "Gym / fitness studio",
    "keywords": ["gym", "fitness", "crossfit", "yoga", "pilates", "boxing", "martial"],
    "template": "gym.html.j2",
    "fonts": ["Anton", "Manrope"],
    "heading_font": "Anton", "body_font": "Manrope",
    "palettes": [
        dict(name="Iron Night", bg="#0D0D0D", surface="#1C1C1E", ink="#FFFFFF", muted="#A8A8AE",
             primary="#1C1C1E", on_primary="#FFFFFF", accent="#D7FF3A", on_accent="#0D0D0D",
             tint="#151517", line="#2C2C2E"),
        dict(name="Ember Energy", bg="#111827", surface="#1B2436", ink="#F5F5F4", muted="#A7B0C0",
             primary="#1E3A8A", on_primary="#FFFFFF", accent="#FF5A1F", on_accent="#111827",
             tint="#0E1522", line="#2A3550"),
    ],
    "h1": "Start training in {city}",
    "sub": "Strength, cardio and coaching under one roof.",
    "chips": ["All levels welcome", "Coach-led classes", "{city_state}"],
    "cta_primary": "Claim my free pass",
    "cta_secondary": "View memberships",
    "offer_badge": "[[Your free-trial offer]]",
    "services_title": "Train your way",
    "services": [
        ("dumbbell", "Strength Training", "Free weights, racks and guided progressions."),
        ("flame", "HIIT & Conditioning", "High-energy interval classes."),
        ("user", "Personal Training", "One-on-one coaching built around your goals."),
        ("users", "Group Fitness Classes", "Motivating, coach-led sessions."),
        ("pulse", "Cardio Zone", "Treadmills, bikes and rowers."),
        ("check", "Beginner Fundamentals", "Learn the basics safely."),
        ("yoga", "Mobility & Recovery", "Flexibility, stretching and recovery."),
        ("key", "Open Gym", "Train on your own schedule."),
    ],
    "steps_title": "How to start",
    "steps": [
        ("Claim your pass", "Tell us your name and number. That is all we need."),
        ("Come in and train", "Meet a coach, look around and try a session."),
        ("Pick a plan", "Choose the membership that fits, or keep training pay-as-you-go. [[Confirm]]"),
    ],
    "extras": {
        "tiers_title": "Memberships",
        "tiers": [
            ("Basic", "$__/mo", ["Open gym access", "[[Edit inclusions]]"], False),
            ("Plus", "$__/mo", ["Everything in Basic", "Group classes", "[[Edit inclusions]]"], True),
            ("Coached", "$__/mo", ["Everything in Plus", "Personal training sessions", "[[Edit inclusions]]"], False),
        ],
        "schedule_title": "Sample weekly schedule",
        "schedule_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "schedule": [
            ("6:00 AM", ["Strength", "HIIT", "Strength", "HIIT", "Strength", "Open", "Rest"]),
            ("12:00 PM", ["Cardio", "Yoga", "Cardio", "Yoga", "Cardio", "Class", "Open"]),
            ("6:00 PM", ["HIIT", "Strength", "Class", "Strength", "HIIT", "Rest", "Open"]),
        ],
        "hours_badge": "[[Open 24/7 or your hours]]",
        "coaches_placeholder": "[[Coach profiles - add photos and bios]]",
        "reviews_placeholder": "[[Member reviews appear here]]",
    },
    "faq": [
        ("Do you offer a free trial or day pass?", "[[Add your trial or day-pass offer]]"),
        ("Is there a contract or sign-up fee, and how do I cancel?", "[[Add your membership terms]]"),
        ("What are your hours? Are you open 24/7?", "[[Add your hours]]"),
        ("I am a beginner. Is that okay?", "Absolutely. Our coaches help new members get started safely. [[Confirm]]"),
        ("Is parking available? What should I bring?", "[[Add parking info]]. Bring water, a towel and comfortable shoes."),
    ],
    "disclaimer": "",
}

NICHES["law"] = {
    "label": "Law firm",
    "keywords": ["law firm", "lawyer", "attorney", "legal", "law office"],
    "template": "law.html.j2",
    "fonts": ["Playfair Display", "Source Sans 3"],
    "heading_font": "Playfair Display", "body_font": "Source Sans 3",
    "palettes": [
        dict(name="Classic Counsel", bg="#F7F4EE", surface="#FFFFFF", ink="#0B1320", muted="#454C58",
             primary="#14213D", on_primary="#FFFFFF", accent="#B08D57", on_accent="#0B1320",
             tint="#EFE9DD", line="#DDD5C4"),
        dict(name="Modern Practice", bg="#FAFAF7", surface="#FFFFFF", ink="#2B2B2B", muted="#555555",
             primary="#1F3D36", on_primary="#FFFFFF", accent="#C9A227", on_accent="#1F3D36",
             tint="#E9EFEA", line="#D9DED8"),
    ],
    "h1": "Trusted legal guidance for {city_state}",
    "sub": "Clear answers and honest advice. [[Edit to reflect your firm]]",
    "chips": ["Local office in {city}", "Confidential consultations", "Straightforward communication"],
    "cta_primary": "Request a consultation",
    "cta_secondary": "Call {phone}",
    "services_title": "Sample practice areas",
    "services": [
        ("family", "Family Law", "Divorce, custody and support guidance."),
        ("doc", "Estate Planning", "Wills, trusts and powers of attorney."),
        ("alert", "Personal Injury", "Help after accidents and injuries."),
        ("scales", "Criminal Defense", "Representation for misdemeanor and felony charges."),
        ("briefcase", "Business Law", "Formation, contracts and disputes."),
        ("home", "Real Estate", "Closings, title and landlord-tenant matters."),
        ("car", "Traffic & DUI", "Tickets and license issues."),
        ("column", "Civil Litigation", "Resolving disputes in and out of court."),
    ],
    "steps_title": "How it works",
    "steps": [
        ("Call or send a message", "Tell us briefly what is going on."),
        ("Consultation", "We listen, ask questions and explain your options."),
        ("Plan of action", "You leave with clear next steps."),
    ],
    "extras": {
        "why_title": "What to expect",
        "why": [
            ("lock", "Confidential", "What you tell us stays between us."),
            ("pin", "Local office", "Right here in {city}. [[Confirm office details]]"),
            ("doc", "Clear communication", "Plain-English answers, not legal jargon."),
        ],
        "form_matters": ["Family", "Estate planning", "Injury", "Criminal", "Business", "Real estate", "Other"],
        "since_placeholder": "Serving {city} since [[year]]",
        "spanish_placeholder": "[[Se habla espanol - if applicable]]",
    },
    "faq": [
        ("How much does a consultation cost?", "[[Add your consultation policy]]"),
        ("How do your fees work?", "Fee structures vary by matter (hourly, flat fee or contingency). [[Add how your firm charges]]"),
        ("What should I bring to my first meeting?", "Bring any documents related to your matter and a list of questions. [[Edit]]"),
        ("How long will my case take?", "Every matter is different. We will give you a realistic outlook after we understand the details."),
        ("Is what I tell you confidential?", "Communications with an attorney are generally protected, but an attorney-client relationship must be established first. Please do not send confidential details through this website."),
    ],
    "disclaimer": "Attorney Advertising. The information on this website is for general information only and is not legal advice. "
                  "Contacting us does not create an attorney-client relationship. Please do not send confidential information until a "
                  "relationship is established.",
}

NICHES["accounting"] = {
    "label": "Accounting / tax firm",
    "keywords": ["accounting", "accountant", "cpa", "tax", "bookkeep"],
    "template": "accounting.html.j2",
    "fonts": ["Lora", "Inter"],
    "heading_font": "Lora", "body_font": "Inter",
    "palettes": [
        dict(name="Trust Blue", bg="#F5F8FA", surface="#FFFFFF", ink="#1F2A33", muted="#4A5661",
             primary="#0F3057", on_primary="#FFFFFF", accent="#F5A623", on_accent="#0F3057",
             tint="#E8F1F5", line="#D5E2EA"),
        dict(name="Growth Green", bg="#F6FAF7", surface="#FFFFFF", ink="#2F3A34", muted="#506057",
             primary="#0B3D2E", on_primary="#FFFFFF", accent="#D4A017", on_accent="#0B3D2E",
             tint="#EAF4EE", line="#D5E5DA"),
    ],
    "h1": "Stress-free tax & accounting in {city_state}",
    "sub": "For individuals and small businesses. Your numbers, handled.",
    "chips": ["Year-round support", "Secure document exchange", "Local to {city}"],
    "cta_primary": "Schedule a consultation",
    "cta_secondary": "Call {phone}",
    "services_title": "Sample services",
    "services": [
        ("receipt", "Individual Tax Preparation", "Federal and state returns, done accurately and on time."),
        ("briefcase", "Business Tax Returns", "For LLCs, S-corps, partnerships and sole proprietors."),
        ("calculator", "Bookkeeping", "Monthly reconciliation and clean books."),
        ("wallet", "Payroll Services", "Payroll processing, filings and year-end forms."),
        ("chart", "Tax Planning", "Strategies to reduce what you owe next year."),
        ("doc", "IRS Notice Help", "Help understanding and responding to letters."),
        ("rocket", "New Business Setup", "Formation guidance and accounting setup."),
        ("users", "Small Business Advisory", "Cash flow, budgeting and entity choice."),
    ],
    "steps_title": "How it works",
    "steps": [
        ("Book a call", "Tell us about your situation."),
        ("Share your documents securely", "Send what we need. [[Add your secure upload method]]"),
        ("We file, report and advise", "We handle the details and explain what they mean."),
    ],
    "extras": {
        "who_title": "Who we help",
        "who": [("user", "Individuals"), ("briefcase", "Small businesses"), ("pen", "Freelancers & self-employed"), ("users", "Nonprofits")],
        "checklist_title": "What to bring to your tax appointment",
        "checklist": [
            "Last year's tax return",
            "W-2s and 1099s",
            "Records of income and expenses",
            "Photo ID",
            "Any IRS or state letters you received",
        ],
        "portal_placeholder": "[[Client portal link]]",
        "since_placeholder": "Serving {city} since [[year]]",
    },
    "faq": [
        ("What documents do I need for my tax return?", "Typically last year's return, W-2s and 1099s, and records of income and expenses. [[Edit for your process]]"),
        ("How much does tax preparation or bookkeeping cost?", "[[Add your pricing approach]]"),
        ("Can you help if I received an IRS letter or have unfiled returns?", "We can help you understand your options. [[Confirm the services you offer]]"),
        ("Do you work with clients remotely?", "[[Confirm - remote clients and secure upload]]"),
        ("Do you offer year-round support or only in tax season?", "[[Add your service availability]]"),
    ],
    "disclaimer": "Content is for general information only and is not tax, legal or accounting advice. "
                  "Contacting us does not establish a client relationship.",
}


def niche_key_for(row: dict) -> str | None:
    """Pick the niche template for a lead row (leads-agent CSV row or dict)."""
    hay = " ".join(str(row.get(k, "")) for k in ("niche_query", "niche", "category", "name")).lower()
    # niche_query is the most reliable, so test it first on its own
    nq = str(row.get("niche_query") or row.get("niche") or "").lower()
    for text in (nq, hay):
        if not text:
            continue
        for key, cfg in NICHES.items():
            if any(k in text for k in cfg["keywords"]):
                return key
    return None
