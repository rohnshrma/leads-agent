import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from leadagent import categorize  # noqa: E402
from leadagent.sources import Business  # noqa: E402

ALL = ["dental clinic", "orthodontist", "med spa", "dermatology clinic", "physiotherapist", "chiropractor",
       "optometrist", "veterinary clinic", "hearing clinic", "psychology clinic", "podiatrist", "massage therapy clinic"]


def g(name, niche, types=""):
    return Business(source="google", source_id=name, name=name, category=types, niche_query=niche)


class DecideTests(unittest.TestCase):
    def check(self, name, niche, types, want, wanted=ALL):
        self.assertEqual(categorize.decide(g(name, niche, types), wanted), want, name)

    def test_real_misfiled_leads_from_the_23_nov_runs(self):
        self.check("Millrose Chiropractic Clinic", "dental clinic", "chiropractor, health", ("relabel", "chiropractor"))
        self.check("Kanda Optical", "dental clinic", "store, health", ("relabel", "optometrist"))
        self.check("Erin Griffin Therapy", "dental clinic", "health", ("relabel", "psychology clinic"))
        self.check("Well from Within Chiropractic", "med spa", "chiropractor", ("relabel", "chiropractor"))
        self.check("New Allergy Clinic", "dental clinic", "doctor, health", ("drop", "nothing shows it is a dental clinic"))
        self.check("Thomas Alton Medical Clinic", "dental clinic", "medical_clinic, doctor", ("drop", "nothing shows it is a dental clinic"))
        self.check("Spartan Krav Maga", "med spa", "gym, sports_club", ("drop", "not one of our business types"))
        self.check("Vixen Nails & Spa | Burlington", "med spa", "nail_salon, spa", ("drop", "not one of our business types"))

    def test_correct_results_are_kept(self):
        self.check("Guelph Line Dental", "dental clinic", "dentist", ("keep", "dental clinic"))
        self.check("Dr. Amanda Jerome", "dental clinic", "dentist, health", ("keep", "dental clinic"))   # name silent, type says so
        self.check("STO Orthodontists", "orthodontist", "dentist", ("keep", "orthodontist"))
        self.check("SkinLogic Medical Spa and Laser", "med spa", "skin_care_clinic", ("keep", "med spa"))
        self.check("Cure Rehab", "physiotherapist", "physiotherapist", ("keep", "physiotherapist"))
        self.check("Roncal Veterinary", "veterinary clinic", "veterinary_care", ("keep", "veterinary clinic"))

    def test_more_specific_name_wins_and_types_relabel(self):
        self.check("Maple Orthodontics & Dental", "dental clinic", "dentist", ("keep", "dental clinic"))
        self.check("Braces Studio Maple", "dental clinic", "dentist", ("relabel", "orthodontist"))
        self.check("Smile Braces Studio", "dental clinic", "dentist", ("keep", "dental clinic"))   # the searched type wins a tie
        self.check("Dr. Lee", "chiropractor", "physiotherapist", ("relabel", "physiotherapist"))
        self.check("Orthotic Lab Woodbridge", "orthodontist", "", ("relabel", "podiatrist"))

    def test_a_relabel_must_be_one_of_the_types_chosen_for_the_run(self):
        self.check("Millrose Chiropractic Clinic", "dental clinic", "chiropractor",
                   ("drop", "nothing shows it is a dental clinic"), wanted=["dental clinic", "med spa"])


class ApplyTests(unittest.TestCase):
    def test_only_google_results_are_checked(self):
        ov = Business(source="overture", source_id="o1", name="Spartan Krav Maga", niche_query="med spa")
        kept, rep = categorize.apply([ov, g("Kanda Optical", "dental clinic"), g("New Allergy Clinic", "dental clinic", "doctor")],
                                     {"niches": ALL})
        self.assertEqual([b.name for b in kept], ["Spartan Krav Maga", "Kanda Optical"])
        self.assertEqual(kept[1].niche_query, "optometrist")
        self.assertEqual(rep, {"wrong_category": 1, "relabelled": 1})


if __name__ == "__main__":
    unittest.main()
