import abc
import numpy as np
import pandas as pd

from pymoo.indicators.hv import HV

from .drsa import DRSA


# ---------------------------------------------------------------------------------------------------------- #
# Base DM template
# ---------------------------------------------------------------------------------------------------------- #
class BaseDM:
    """
    BaseDM provides the abstract interface for a decision maker (DM) used in an
    iterative preference elicitation loop. Subclasses must implement classify,
    select, and is_satisfied methods to drive the loop.
    """

    @abc.abstractmethod
    def classify(self, F_pareto: np.ndarray, X_pareto: np.ndarray, assoc_rules_summary: str = None):
        """
        Classify Pareto sample into 'good' (2) vs 'other' (1) via median-split.
        Chooses the objective whose split yields the most balanced classes.

        :param X_pareto:
        :param F_pareto: array of shape (n_samples, n_objectives)
        :param assoc_rules_summary: str the summary of the association rules
        :return: array of labels (1 or 2) for each sample in T
        """
        pass

    @abc.abstractmethod
    def select(self, rules):
        """
        Selects a subset of induced DRSA rules based on scoring method.

        :param rules: list of decision rules, each as a tuple
        :return: chosen subset of rules
        """
        pass

    @abc.abstractmethod
    def select_reduct(self, reducts, core):
        """
        Select which reduct should be used in the DRSA algorithm.

        :param reducts: tuple of all reducts, each as a tuple
        :param core: tuple of core decision rules
        """
        pass

    @abc.abstractmethod
    def is_satisfied(self, X, T, rules) -> bool:
        """
        Determine whether the engine should stop the preference elicitation loop.

        :param X: current Pareto front in decision space (unused here)
        :param T: current Pareto set in objective space
        :param rules: selected DRSA rules
        :return: True to stop, False to continue
        """
        pass

    def simple_score(self, rules, k=5, alpha=0.7):
        """
        Score and select top-k rules based on a weighted combination of rule support
        and confidence for 'certain' rules.

        :param rules: list of DRSA rules, each tuple contains (conditions, conclusions, support, confidence, type, ...)
        :param k: number of rules to select
        :param alpha: weight for confidence vs support (0 <= alpha <= 1)
        :return: top-k scored rules
        """
        scored = [(alpha * r[3] + (1 - alpha) * r[2], r) for r in rules if r[4] == 'certain']
        scored.sort(reverse=True, key=lambda x: x[0])

        return [r for (_, r) in scored[:k]]

    def select_pareto(self, rules):
        """
        Select Pareto-optimal rules based on support and confidence for 'certain' rules.

        :param rules: list of DRSA rules
        :return: Pareto-optimal subset of rules
        """
        certain = [r for r in rules if r[4] == 'certain']
        pareto = []
        for r in certain:
            s1, c1 = r[2], r[3]
            dominated = any((s2 >= s1 and c2 >= c1) and (s2 > s1 or c2 > c1) for (_, _, s2, c2, _, _, _) in certain)

            if not dominated:
                pareto.append(r)

        return pareto

    def is_interactive(self) -> bool:
        """
        :return: True if the DM is interactive, False otherwise
        """
        return False

    def print_samples(self, pareto_set_sample, pareto_front_sample):
        pass


# ---------------------------------------------------------------------------------------------------------- #
# Interactive DM
# ---------------------------------------------------------------------------------------------------------- #
class InteractiveDM(BaseDM):
    """
    An interactive Decision Maker that guides a human-in-the-loop
    preference elicitation process over Pareto-optimal samples using association
    and decision rules.
    """

    def classify(self, F_pareto: np.ndarray, X_pareto: np.ndarray, assoc_rules_summary: str = None) -> np.ndarray:
        """
        Prompt the user to classify Pareto-optimal samples into 'good' or 'other'.
        Displays association rules and current Pareto sample for context.

        :param X_pareto:
        :param F_pareto: objective values of Pareto-optimal samples (n_samples, n_objectives)
        :param assoc_rules_summary: association rules for context
        :return: array of labels (2 for 'good', 1 for 'other')
        """
        if assoc_rules_summary is None or assoc_rules_summary == "" or assoc_rules_summary == "\n":
            print("\nIt appears there is no strong or relevant correlation between the objective function.")
        else:
            print("\nAssociation Rules:")
            print(assoc_rules_summary)

        self.print_samples(F_pareto, X_pareto)

        prompt = "\nSelect indices (#) of samples with 'good' evaluation (comma-separated) \n(Press Enter if none are satisfactory): \n"

        while True:
            selection = input(prompt).strip()
            if not selection:
                good_idxs = set()
                break

            tokens = [tok.strip() for tok in selection.split(',') if tok.strip()]
            invalids = []
            good_idxs = set()

            for tok in tokens:
                if not tok.isdigit():
                    invalids.append(tok)
                    continue
                i = int(tok)
                if 0 <= i < len(F_pareto):
                    good_idxs.add(i)
                else:
                    invalids.append(tok)

            if invalids:
                print("Invalid input. Please enter valid sample indices (0 to "
                      f"{len(F_pareto) - 1}), separated by commas.")
                continue

            break

        labels = np.ones(len(F_pareto), dtype=int)
        for i in good_idxs:
            if 0 <= i < len(F_pareto):
                labels[i] = 2

        return labels

    def print_samples(self, pareto_set_sample, pareto_front_sample):
        data = []
        for idx, obj in enumerate(pareto_set_sample):
            x_vals = np.atleast_1d(pareto_front_sample[idx])
            o_vals = np.atleast_1d(obj)

            fmt = lambda seq: "[" + ", ".join(f"{v:.4f}" for v in seq) + "]"

            var_str = fmt(x_vals)
            obj_str = fmt(o_vals)

            row = {"# ": f"[{idx}]", " [x_1, ..., x_n]": var_str, " [f_1(x), ..., f_m(x)]": obj_str}
            data.append(row)

        df = pd.DataFrame(data)
        print("\nCurrent Pareto sample (X) and their evaluation (F(X)):")
        print(df.to_string(justify='middle', index=False))
        

    def select_reduct(self, reducts, core):
        assert reducts is not None, "Reducts list is empty, iteration was not skipped!"

        if len(reducts) == 1:
            return reducts[0]

        elif len(reducts) > 1:
            print("Available Reducts:")

            for idx, red in enumerate(reducts):
                print(f"[{idx}] {red}")

            print(f"Core criteria (must keep): {core}")

            selected_idx = input("Select reduct by index (default 0): ").strip()
            selected_idx = int(selected_idx) if selected_idx.isdigit() else 0
            selected_reduct = reducts[selected_idx]

        else:
            selected_reduct = reducts[0]

        return selected_reduct

    def select(self, rules):
        """
        Prompt the user to select which induced DRSA rules to enforce next iteration.

        :param rules: list of induced decision rules
        :return: subset of rules selected by the user
        """
        assert rules is not None, "Rule list is empty, iteration was not skipped!"

        # 1) Show the available rules
        print("\nBased on your selection, the following Decision Rules were induced:")
        _ = DRSA.explain_rules(rules, verbose=True)

        prompt = "\nSelect rule(s) to enforce in the next iteration (comma-separated) \n(Press enter to skip): "

        while True:
            selection = input(prompt).strip()

            if not selection:
                return []

            tokens = [tok.strip() for tok in selection.split(',')]
            chosen = []
            invalids = []

            for tok in tokens:
                if not tok.isdigit():
                    invalids.append(tok)
                    continue

                i = int(tok)
                if 0 <= i < len(rules):
                    rule = rules[i]
                    if rule not in chosen:
                        chosen.append(rule)
                else:
                    invalids.append(tok)

            if invalids:
                print(f"Invalid selection(s): {', '.join(invalids)}.  Please try again.\n")
                continue

            return chosen



    def is_satisfied(self, X, T: np.ndarray, rules) -> bool:
        """
        Prompt the user to indicate if any solution from the new Pareto sample is satisfactory.

        :param X: decision space points (unused)
        :param T: objective values of new Pareto sample
        :param rules: enforced DRSA rules (unused)
        :return: True if the user selects a solution to end, False otherwise
        """
        selection = input("\nWould you like to terminate? (y, n): ")

        if selection.strip().lower() == 'y':
            return True

        print("\nContinuing to next iteration...")
        return False

    def is_interactive(self):
        return True

# ---------------------------------------------------------------------------------------------------------- #
# Automated DM
# ---------------------------------------------------------------------------------------------------------- #
class AutomatedDM(BaseDM):
    """
    Automated Decision Maker for IMO-DRSA.
    Automatically classifies, selects rules, and decides stopping without human input.
    Primarily used for test problems or known optimal procedures.
    """

    def __init__(self, max_rounds: int = 3, vol_eps: float = 1e-3, score: str = 'simple'):
        """
        Initialize the automated decision maker.

        :param max_rounds: maximum number of iterations before stopping
        :param vol_eps: hypervolume convergence threshold
        :param score: scoring method ('simple' or 'pareto')
        """
        self.hv_indicator = None
        self.max_rounds = max_rounds
        self.vol_eps = vol_eps
        self.score = score  # 'pareto' or 'simple'
        self.prev_rules = None
        self.prev_hv = None
        self.round = 0

    def classify(self, F_pareto: np.ndarray, X_pareto, assoc_rules_summary=None) -> np.ndarray:
        """
        Automatically classify samples via median-split on objectives for balanced labels,
        compute initial hypervolume indicator.

        :param X_pareto:
        :param F_pareto: objective values of Pareto-optimal samples
        :param assoc_rules_summary: association rules (unused)
        :return: labels array where 2 indicates better than median
        """
        medians = np.median(F_pareto, axis=0)
        n_points, n_objs = F_pareto.shape
        best_balance = n_points + 1
        best_labels = np.ones(n_points, dtype=int)

        for i in range(n_objs):
            labels = np.where(F_pareto[:, i] <= medians[i], 2, 1)
            balance = abs((labels == 2).sum() - (labels == 1).sum())
            if balance < best_balance:
                best_balance = balance
                best_labels = labels

        ref_point = np.max(F_pareto, axis=0) * (1 + 0.05)  # margin = 0.05
        self.hv_indicator = HV(ref_point)

        hv_value = self.hv_indicator(F_pareto)
        self.prev_hv = hv_value

        return best_labels

    def select(self, rules):
        """
        Choose rules based on configured scoring strategy.

        :param rules: list of induced decision rules
        :return: selected subset of rules
        """
        if self.score == 'simple':
            return self.simple_score(rules)

        elif self.score == 'pareto':
            return self.select_pareto(rules)

        return rules

    def select_reduct(self, reducts, core):
        return min(reducts, key=len)

    def is_satisfied(self, X, T: np.ndarray, rules) -> bool:
        """
        Determine stopping condition based on:
        1) number of solutions <= 1
        2) hypervolume change < vol_eps
        3) unchanged rule set
        4) reaching max_rounds

        :param X: decision space points (unused)
        :param T: objective values of Pareto-optimal samples
        :param rules: selected DRSA rules
        :return: True if stopping condition met, False otherwise
        """
        # 1) no or single solution
        if T.shape[0] <= 1:
            return True

        # 2) Hypervolume convergence
        hv = self.hv_indicator(T)
        if self.prev_hv is not None and abs(hv - self.prev_hv) < self.vol_eps:
            return True
        self.prev_hv = hv

        # 3) stable rule set
        if self.prev_rules is not None and rules == self.prev_rules:
            return True
        self.prev_rules = list(rules)

        # 4) fallback to max rounds
        self.round += 1
        return self.round >= self.max_rounds


# ---------------------------------------------------------------------------------------------------------- #
# Dummy DM (for unit tests)
# ---------------------------------------------------------------------------------------------------------- #
class DummyDM(BaseDM):
    """
    Dummy Decision Maker for unit tests.
    Provides trivial classification and selection logic without interaction.
    """

    def __init__(self):
        """
        Initialize the dummy decision maker.
        """
        self.round = 0
        self.score = 'pareto'

    def classify(self, F_pareto, X_pareto, assoc_rules_summary=None):
        """
        Dummy classification: always returns label 1 for all samples.

        :param X_pareto:
        :param F_pareto: objective values (unused)
        :param assoc_rules_summary: (unused)
        :return: label array of ones
        """
        n, m = F_pareto.shape
        return np.ones(n, dtype=int)

    def select(self, rules):
        """
        Choose rules based on configured scoring strategy.

        :param rules: list of DRSA rules
        :return: selected rules
        """


        return rules


    def select_reduct(self, reducts, core):
        return reducts[0]

    def is_satisfied(self, X, T, rules) -> bool:
        """
        Dummy stopping: stops after 3 rounds.

        :param X: (unused)
        :param T: (unused)
        :param rules: (unused)
        :return: True if 1 rounds completed, False otherwise
        """

        return True
