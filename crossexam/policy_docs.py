"""Short generic guidance snippets for retrieval. Written for this project, not copied from any regulator."""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

SNIPPETS = {
    "P1": "Structuring: repeated cash deposits kept just under a reporting threshold, followed by onward transfers, can indicate structuring. "
          "Legitimate cash businesses show the same deposit pattern for many months and it matches their stated activity.",
    "P2": "Layering: money that enters an account and leaves within hours or days in almost the same amount, passing through several accounts, can indicate layering.",
    "P3": "Circular flows: funds that return to their origin through a short loop of accounts may indicate circular flows. "
          "Family members moving allowances around a loop is a common legitimate pattern when the relationship is documented.",
    "P4": "Mule accounts: an account that receives many payments from unrelated senders and forwards most of the money to one recipient may be a mule account. "
          "Marketplace sellers also receive many small payments, but they pay out to their own accounts and have a stable history.",
    "P5": "Sudden activity: an account with little history that suddenly receives large sums and moves them out quickly deserves review, whatever the typology.",
    "P6": "Documented events: a large one-off inflow from a documented event such as a property sale, that is then spent on loans, taxes and purchases, is generally explainable when documentation exists.",
    "P7": "Stable history: activity that matches the customer's own earlier months and expected volume lowers concern, but does not remove it when other warning signs exist.",
}


class PolicySearch:
    def __init__(self):
        self.ids = list(SNIPPETS)
        self.vec = TfidfVectorizer(stop_words="english", sublinear_tf=True)
        self.X = self.vec.fit_transform([SNIPPETS[i] for i in self.ids])

    def top(self, query: str) -> str:
        sims = cosine_similarity(self.vec.transform([query]), self.X).ravel()
        return self.ids[int(sims.argmax())]
