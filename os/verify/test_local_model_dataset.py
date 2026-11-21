"""Verify local model dataset split and safety without network or weights."""
import sys
from pathlib import Path
import unittest

TRAIN=Path(__file__).resolve().parents[1]/"model/training"
sys.path.insert(0,str(TRAIN))
from validate_dataset import load_validate

class TrainingDataTest(unittest.TestCase):
    def test_examples_are_explicitly_synthetic_and_split(self):
        train,holdout=load_validate(TRAIN/"synthetic_intents.jsonl")
        self.assertGreaterEqual(len(train),10)
        self.assertGreaterEqual(len(holdout),6)
        self.assertTrue(all(row["expected"]["requiresReview"] == (row["expected"]["tool"] != "refuse")
                            for row in holdout.values()))
        self.assertEqual(sum(x["expected"]["tool"] == "refuse" for x in holdout.values()),2)
        self.assertFalse(any(row["expected"]["executed"] for row in holdout.values()))

if __name__=="__main__":
    unittest.main()
