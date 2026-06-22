# Cognitive Resources for Neural Planning: Which Algorithms Do Vision, Language, and Tools Afford?

**ICLR 2027 Research Proposal**  
*A Diagnostic Study on Multimodal Planning Algorithm Learnability*

---

## 1. Abstract

Large language models can write A* pseudocode, yet fail to execute it on visual puzzles. Vision-language models achieve 9% success on Blocksworld planning, while humans with paper and pencil routinely solve harder variants. This disparity is not merely a capacity gap—it is an **architectural mismatch**. BFS, A*, and Graphplan were designed for machines with exact memory, deterministic state hashing, and random-access storage. They are not algorithms for soft pattern matchers with limited context windows.

Cognitive science offers a radical alternative: humans do not plan by executing BFS in their heads. We plan through **heuristic perception** (Gibson, 1979), **hierarchical language** (Carruthers, 2002), and **external scaffolding** (Clark & Chalmers, 1998). Each cognitive resource affords a distinct species of planning. Yet the AI community treats multimodal LLMs as cognitively homogeneous—feeding them pixels, text, and API calls, then wondering why they uniformly fail at systematic search.

We propose a diagnostic study that treats this failure as **ecological**: different input modalities induce different algorithmic biases. We freeze a lightweight world model and systematically vary the planner's access to vision, language, and external scratchpad memory, measuring not just *"does it plan?"* but **"which algorithm does it converge to?"** Our central hypothesis is that no single modality dominates all algorithms; instead, vision, language, and tools occupy distinct regions of a **learnability manifold** that predicts which algorithms are natively learnable, which require scaffolding, and which are structurally incompatible with given resource constraints.

We further test the **Algorithmic Bias Transfer Hypothesis**: planning biases learned under specific resource configurations in Blocksworld will transfer to distinct reasoning domains—mathematical proof (FOLIO), code debugging (HumanEval), and scientific hypothesis generation—predicting characteristic failure modes (e.g., visual-trained heuristic bias producing shallow reasoning in math).

Our experiments compress the algorithm space into four cognitively diagnostic families—**BFS** (systematic enumeration), **Fast Forward** (delete-relaxation heuristic search), **Iterated Width** (novelty-based structured exploration), and **Graphplan** (constraint propagation over proposition layers)—across four modality configurations (Vision, Language, VLA, VLA+Tool). We include a **zero-shot diagnostic** to distinguish *algorithmic knowledge* (what the model knows) from *algorithmic affordance* (what the modality extracts).

---

## 2. Theoretical Framework

### 2.1 The Computational Resource Substitution Hypothesis (CRSH)

We operationalize the cognitive science framing as a **testable, falsifiable computational hypothesis**:

> **CRSH:** Human cognitive resources (perception, language, tools) are *partially substitutable* in planning. When one resource is absent, others can compensate by increasing computational cost. However, for specific algorithms, substitution encounters **hard boundaries** beyond which compensation fails. These boundaries are determined by the representational format of the resource, not by model capacity.

#### 2.1.1 Formal Definitions

Let $\mathcal{R} = \{V, L, T\}$ be the set of cognitive resources (Vision, Language, Tool). Let $\mathcal{A} = \{B, F, I, G\}$ be the algorithm families (BFS, Fast Forward, Iterated Width, Graphplan). Let $M: \mathcal{R} \times \mathcal{A} \to [0,1]$ be the **learnability function**, measuring the probability that a planner with resource $r$ converges to algorithm $a$ with success rate $\geq 0.8$ within $N$ training steps.

**Definition 1 (Soft Boundary):** A resource $r$ has a **soft boundary** for algorithm $a$ if there exists a resource $r' \neq r$ such that:
$$M(r, a) < \tau \quad \text{but} \quad M(r \cup r', a) \geq \tau$$
where $\tau = 0.8$ is the success threshold. This means $r$ alone is insufficient but can be compensated.

**Definition 2 (Hard Boundary):** A resource $r$ has a **hard boundary** for algorithm $a$ if for all $r' \subseteq \mathcal{R} \setminus \{r\}$:
$$M(r', a) < \tau$$
That is, no combination of other resources can compensate for the absence of $r$.

**Definition 3 (Resource Redundancy):** Two resources $r_1, r_2$ are **redundant** for algorithm $a$ if:
$$M(r_1, a) \approx M(r_2, a) \approx M(r_1 \cup r_2, a)$$
This falsifies the cognitive specificity claim for that algorithm.

#### 2.1.2 Pre-Registered Hard Boundary Predictions

| Missing Resource | Compensating Resource | Algorithm | Predicted Boundary Type | Mechanism |
|-----------------|----------------------|-----------|------------------------|-----------|
| Tool (external memory) | Language (self-talk) | BFS | **Hard** | Context window overflow; FIFO queue requires $O(b^d)$ state retention impossible in bounded self-attention |
| Language (abstraction) | Tool (memory-intensive) | Graphplan | **Hard** | Proposition-level graph construction requires structured symbolic vocabulary; pure memory cannot invent propositions |
| Vision (heuristic pattern) | Language (symbolic heuristic) | Fast Forward | **Soft** | Delete-relaxation heuristic can be approximated symbolically, but visual affordances provide faster perceptual shortcuts |
| Language (state representation) | Vision (perceptual grouping) | Iterated Width | **Soft** | Novelty detection benefits from both abstract state descriptions and perceptual feature grouping; either can partially compensate |
| Vision + Language | Tool | Any | **Soft** | Tools provide memory but cannot generate heuristics or abstractions; required for all algorithms but sufficient for none |

**Falsification Condition:** If any predicted hard boundary is violated (e.g., Vision-only achieves BFS success $\geq 0.8$), CRSH is falsified for that boundary.

### 2.2 Cognitive Resource-Algorithm Mapping: Detailed Argumentation

We do not claim that our scratchpad is equivalent to Clark & Chalmers' extended mind, nor that rendered pixels capture Gibson's direct perception. Rather, we treat these frameworks as **heuristic metaphors** to guide experimental design, with explicit operationalization at the functional level.

#### 2.2.1 Vision → Fast Forward (Gibsonian Affordance)

**Gibson's claim:** Perception is not passive reception but active extraction of **affordances**—action possibilities directly perceived in the environment. A chair "affords" sitting; a gap "affords" crossing.

**Operationalization:** In Blocksworld, a rendered image of a tower of blocks **affords** a "collapse" heuristic: the visual gestalt of height and instability directly suggests "remove bottom block" without symbolic reasoning. This is **pattern completion**, not systematic search. Fast Forward's delete-relaxation heuristic—estimating the cost to achieve all goals simultaneously—is a natural fit for visual pattern matching: the visual system can rapidly estimate "how much is left to do" from the current arrangement.

**Algorithmic prediction:** Vision-only will converge to **Fast Forward** because:
- The visual cortex (simulated by CNN/ViT features) is optimized for spatial pattern matching and rapid holistic estimation.
- Delete-relaxation produces a scalar heuristic that directly mirrors visual gestalt perception: "the whole scene looks closer to/distant from the goal."
- The greedy, locally optimal expansion strategy of Fast Forward mirrors visual attention: fixating on the most salient/out-of-place object.

**Why not systematic algorithms?** Visual working memory in humans is limited to 3-4 objects (Luck & Vogel, 1997). A FIFO queue of $10^3$ states or a novelty table requiring exact state identity is architecturally alien to visual processing. We predict Vision-only BFS and IW will fail due to **memory overflow** (states forgotten) or **heuristic fixation** (greedy collapse into FF-like behavior even when prompted otherwise).

#### 2.2.2 Language → Graphplan (Carruthers' Hierarchical Composition)

**Carruthers' claim:** Language is not merely communication but a **cognitive architecture** for hierarchical, recursive thought. It enables "thinking about thinking" (metacognition) and compositional abstraction.

**Operationalization:** PDDL predicates like `(on A B)`, `(clear C)`, `(goal (on D E))` are **hierarchical symbolic tokens** that can be composed into proposition layers. Natural language descriptions ("Block A is on Block B; to move it, I must first clear Block C") mirror this compositional structure.

**Algorithmic prediction:** Language-only will converge to **Graphplan** because:
- Proposition layers are **isomorphic to linguistic phrase structures**: Layer 0 = initial state (lexical items), Layer 1 = achievable propositions (phrases), Layer 2 = goal propositions (sentences).
- Mutex relations are **linguistic negation constraints**: "Block A cannot be on B and on C simultaneously" is a direct translation of mutual exclusion.
- BFS and IW underutilize language's compositional power; Fast Forward underutilizes its constraint-expression capability.

**Why not other algorithms?** Language provides abstraction, but BFS requires **state enumeration without abstraction**, IW requires **exact identity checking**, and Fast Forward requires **perceptual gestalt**. Using language for these is like using a dictionary to do arithmetic—possible but mismatched.

#### 2.2.3 Tool → BFS and Iterated Width (Clark & Chalmers' Extended Mind)

**Clark & Chalmers' claim:** Cognitive processes extend beyond the brain into the environment. A notebook used by an Alzheimer's patient is not a mere aid but **constitutive of memory**.

**Operationalization:** Our `read/write` scratchpad is a minimal extended memory. It does not "help" the model remember; it **constitutes** the memory for algorithms that require external state storage.

**Algorithmic prediction:** Tool-only (and VLA+Tool) will converge to **BFS** and **Iterated Width** because:
- BFS requires a **FIFO queue** of $O(b^d)$ states. The scratchpad `write("queue", state_id)` externalizes this queue, transforming an $O(b^d)$ memory demand into an $O(1)$ internal state + $O(b^d)$ external storage.
- Iterated Width requires a **novelty table** tracking which atomic conjunctions have been seen. The scratchpad externalizes this table.
- Without the tool, the model's context window (32K tokens) is a **bounded working memory**. For Blocksworld with 10 blocks, the state space is $>10^{10}$; the context window cannot hold the BFS frontier or the IW novelty table.

**Why not heuristic algorithms?** Tools provide memory, not pattern matching or abstraction. A scratchpad with queue operations does not provide heuristic values (FF) or mutex constraints (Graphplan); it only provides storage.

#### 2.2.4 VLA → Balanced Integration

**Prediction:** VLA without tools will converge to a **hybrid** strategy: using vision for Fast Forward-like heuristic estimation and language for structural reasoning. However, with tools, VLA+Tool can implement all four algorithms by delegating memory-intensive components (BFS/IW) to the scratchpad while preserving heuristic (vision) and constraint (language) capabilities.

**Why this is the integration test:** If VLA+Tool achieves high success on all four algorithms while unimodal configurations fail on specific ones, this proves **modality-specificity** rather than **modality-additivity**: the tools provide the memory substrate, but vision and language each contribute irreplaceable algorithmic biases.

---

## 3. Research Questions

### RQ1: Algorithmic Knowledge vs. Algorithmic Affordance
Do multimodal transformers possess algorithmic knowledge in pre-trained weights (can they write BFS/FF/IW/Graphplan pseudocode zero-shot), and does the input modality determine whether that knowledge is *afforded* (extractable) for execution? We test this via a **zero-shot diagnostic** before supervised fine-tuning: we prompt Qwen2.5-VL-3B to execute BFS, Fast Forward, Iterated Width, and Graphplan under each modality condition without task-specific training.

**Operationalization:** If the model generates syntactically correct BFS pseudocode in text-only zero-shot but achieves $<5\%$ success on visual Blocksworld, this demonstrates **knowledge-affordance decoupling**: the algorithm is in the weights, but the modality gates its extraction.

### RQ2: Asymmetric Repair and Learnability Manifolds
How do vision, language, and tools asymmetrically repair the failure modes of different algorithms? Do they provide complementary capabilities, or do they interfere?

**Operationalization:** We measure **convergence dynamics** (sample efficiency curves) and **failure mode signatures** (error taxonomies: memory overflow, heuristic fixation, constraint violation, novelty collapse) to map each modality to its **learnability manifold**—the region of algorithmic space where it induces stable convergence.

### RQ3: The Pareto Hypothesis and Hard Boundaries
Do multimodal combinations exhibit a genuine Pareto frontier between operational precision (single-step accuracy) and structural generalization (length/compositional transfer)? Or does "more modalities" uniformly improve all algorithms?

**Operationalization:** If VLA+Tool uniformly dominates all metrics, we test whether **learning dynamics** (convergence speed, exploration patterns) still exhibit irreducible modality-specific signatures, preserving CRSH at the process level even if performance differences collapse.

### RQ4: Algorithmic Bias Transfer
Do planning biases learned under specific resource configurations transfer to non-planning reasoning tasks? Specifically, does a planner trained with vision-only Fast Forward exhibit **shallow, pattern-matching errors** in mathematical proof (FOLIO), while a planner trained with language-only Graphplan exhibits **systematic but brittle constraint reasoning** in code debugging (HumanEval)?

**Operationalization:** Zero-shot performance on target tasks after freezing the planner. If characteristic failure modes from planning transfer to reasoning, this demonstrates that **algorithmic bias is a transferable cognitive trait**.

---

## 4. Research Gap Assessment

### 4.1 Verified Closest Work

| No. | Title | Identifier | Relation to Our Work |
|-----|-------|-----------|---------------------|
| [1] | BISON: Learning Bilevel Policies over Symbolic World Models | arXiv:2605.15975 | Uses symbolic world models; we freeze world models to isolate planning |
| [2] | RAP: Reasoning via Planning | EMNLP 2023 | Text-only MCTS; no multimodal or algorithm-family comparison |
| [3] | LLM-MCTS | NeurIPS 2023 | Text-only search; no vision or tool scaffolding |
| [4] | SCOPE | arXiv:2512.09897 | Hierarchical text planning; no cross-algorithm diagnostic |
| [5] | VLA-JEPA | arXiv:2602.10098 | VLA world model; not a planning algorithm study |
| [6] | ViPlan | arXiv:2505.13180 | Shows VLA fails at 9%; we ask *why* by algorithm family |
| [7] | LeWorldModel | arXiv:2603.19312 | Our frozen backbone for continuous domains |
| [8] | DELTA | 2024 | Uses external planners; we learn planning algorithms natively |

### 4.2 Why This Is Not an Ablation Study

Existing work asks: *"Can LLMs plan?"* or *"Does adding vision help?"* We ask: **"Given that LLMs are soft pattern matchers, which planning algorithms should we expect them to learn natively under which resource constraints?"** This is not an ablation of modalities on a fixed algorithm. It is a **systematic excavation of algorithmic affordances**—mapping the inductive bias of multimodal transformers onto the algorithmic space of planning. Our four-algorithm design (BFS, Fast Forward, Iterated Width, Graphplan) spans the full spectrum from systematic search to heuristic to constraint-based planning, ensuring no major planning paradigm is left unexplored.

---

## 5. Methodology

### 5.1 Zero-Shot Diagnostic Protocol (Pre-Training Probe)

Before any SFT, we conduct a **zero-shot / few-shot diagnostic** to test CRSH's knowledge-affordance decoupling. This protocol is designed to be executable in **48 hours** and determines whether the core hypothesis is viable.

#### 5.1.1 Prompt Design

For each algorithm $a \in \{BFS, FF, IW, Graphplan\}$ and each modality $m \in \{V, L, VLA, VLA+T\}$, we construct a **structured prompt** with three components:

**Component 1: Algorithm Definition (Fixed across modalities)**
```
You are executing [ALGORITHM] on a Blocksworld task.
[ALGORITHM_DEFINITION]
BFS: Maintain a queue of states. Dequeue the front state. If it is the goal, return. Otherwise, enqueue all valid successor states. Repeat.
Fast Forward: Compute the delete-relaxation heuristic: assume all negative effects are ignored. Estimate distance to goal. Expand the most promising state greedily.
Iterated Width: Maintain a novelty table. For width k, expand a state only if it introduces a new k-atom conjunction not seen before. Increase k if no new states.
Graphplan: Build proposition layers. Layer 0 = initial state. Layer k+1 = all propositions achievable by applying one action to layer k. Add mutex relations for incompatible propositions. Stop when goal propositions appear in a layer without mutex.
```

**Component 2: Modality-Specific Input**

| Modality | Input Format |
|----------|-------------|
| **Vision-only** | Rendered 256×256 RGB image of current Blocksworld state + "Execute the next step of [ALGORITHM]" |
| **Language-only** | PDDL state description: `(on a b), (on b c), (clear d), (handempty)` + natural language goal + "Execute the next step of [ALGORITHM]" |
| **VLA** | Both image and PDDL text simultaneously |
| **VLA+Tool** | Above + scratchpad state: `Queue: [state_1, state_2]; Visited: [state_0]; Novelty: [atoms_seen]` |

**Component 3: Output Format Constraint**
```
Respond in the following JSON format:
{
  "algorithm": "[ALGORITHM_NAME]",
  "next_action": "pickup(X) / stack(X,Y) / unstack(X,Y) / putdown(X)",
  "internal_state_update": "[describe queue/heuristic value/novelty table/proposition layer update]",
  "confidence": 0.0-1.0
}
```

#### 5.1.2 Evaluation Criteria

A trial is **successful** if:
1. **Syntactic validity:** Output is parseable JSON with required fields.
2. **Algorithmic fidelity:** The `internal_state_update` correctly reflects one step of the target algorithm (e.g., for BFS, the queue is updated FIFO; for FF, the heuristic is computed from delete-relaxation; for IW, novelty is checked; for Graphplan, mutexes are correctly identified).
3. **Action validity:** The `next_action` is legal in the current state.

**Scoring:**
- **Pass:** All three criteria met.
- **Algorithmic Error:** Criteria 1 and 3 met, but 2 failed.
- **Action Error:** Criterion 1 met, but 3 failed.
- **Parse Error:** Criterion 1 failed.

#### 5.1.3 Diagnostic Decision Matrix

| Result Pattern | Interpretation | Action |
|---------------|----------------|--------|
| Text-only Pass, Vision-only Fail | **Knowledge-Affordance Decoupling confirmed** | Proceed with full SFT |
| All modalities Pass | Algorithm too easy; may not discriminate resources | Increase task difficulty (more blocks, longer horizon) |
| All modalities Fail | Model lacks algorithmic knowledge | Switch to "algorithm discovery" framing: which approximation does each modality discover? |
| Tool-only Pass for BFS/IW, others Fail | External memory is necessary and sufficient for systematic search | Validate CRSH hard boundary for BFS/IW |

### 5.2 Algorithm Family Implementation Details

We implement four algorithms with explicit **state-action trajectories** for SFT. Each algorithm is operationalized as a **policy** $\pi_m(a | s, \text{scratchpad})$ conditioned on modality $m$.

#### 5.2.1 Algorithm 1: Breadth-First Search (BFS) with Tool-Template

**Algorithm:** Breadth-First Search with external FIFO queue.

**Tool-Template Protocol:**
```python
def bfs_step(scratchpad, current_state):
    queue = scratchpad.read("queue")      # External memory read
    visited = scratchpad.read("visited")
    
    if not queue:
        return "FAIL"
    
    state_id = queue.pop(0)               # FIFO dequeue
    state = decode_state(state_id)
    
    if is_goal(state):
        return "SUCCESS"
    
    for action in legal_actions(state):
        next_state = transition(state, action)
        next_id = encode_state(next_state)
        if next_id not in visited:
            queue.append(next_id)         # FIFO enqueue
            visited.add(next_id)
    
    scratchpad.write("queue", queue)      # External memory write
    scratchpad.write("visited", visited)
    
    return action                         # Action to execute
```

**Training Data Format:**
```
Input:  [RENDERED_IMAGE or PDDL_TEXT] + scratchpad_state
Output: {
  "action": "pickup(a)",
  "scratchpad_update": {
    "queue": ["state_0", "state_3", "state_7"],
    "visited": ["state_0", "state_1", "state_2"]
  }
}
```

**Why this is a hard boundary test:** BFS requires $O(b^d)$ queue storage. Without the tool, the model must maintain the queue in its context window. For 10 blocks, $b \approx 50$, $d = 5$, queue size $> 10^6$ states—impossible in 32K tokens. With the tool, the model only needs to store the queue pointer and current state.

#### 5.2.2 Algorithm 2: Fast Forward (FF) with Delete-Relaxation Heuristic

**Algorithm:** Greedy best-first search with delete-relaxation heuristic (Hoffmann & Nebel, 2001).

**Heuristic Design:**
- **Vision:** Heuristic is a **learned value head** on the visual encoder: $h_{vis}(s) = MLP(ViT(image))$ that estimates relaxed plan length.
- **Language:** Heuristic is computed **symbolically** by counting unsolved goals with relaxed preconditions: $h_{lang}(s) = |\text{goals not achieved in relaxed reachability}|$.
- **VLA:** Heuristic is $h_{vla}(s) = \alpha h_{vis}(s) + (1-\alpha) h_{lang}(s)$, with $\alpha$ learned.

**Algorithm Protocol:**
```python
def ff_step(state, scratchpad):
    # Compute delete-relaxation heuristic
    relaxed_plan = compute_relaxed_plan(state, goals)
    h_value = len(relaxed_plan)
    
    # Generate successors
    successors = []
    for action in legal_actions(state):
        next_state = transition(state, action)
        h_next = compute_relaxed_plan(next_state, goals)
        successors.append((next_state, action, h_next))
    
    # Greedy selection: expand state with minimal h
    best = min(successors, key=lambda x: x[2])
    
    scratchpad.write("h_value", h_value)
    return best.action
```

**Training Data Format:**
```
Input:  [IMAGE and/or TEXT] + current_h_value
Output: {
  "action": "stack(a,b)",
  "heuristic_value": 4.2,
  "relaxed_plan_length": 4,
  "priority": "HIGH"
}
```

**Why FF is essential:** Fast Forward represents **greedy, perception-driven planning** where the heuristic is a rapid estimate of "how much work remains." This aligns with visual pattern matching, making it the ideal algorithm for Vision-only conditions.

#### 5.2.3 Algorithm 3: Iterated Width (IW) with Novelty Table

**Algorithm:** Iterated Width search with novelty-based pruning (Lipovetzky & Geffner, 2012).

**Tool-Template Protocol:**
```python
def iw_step(scratchpad, current_state, width_k):
    novelty_table = scratchpad.read("novelty_table")
    visited = scratchpad.read("visited")
    frontier = scratchpad.read("frontier")
    
    # Extract all k-atoms from current state
    atoms = extract_atoms(current_state, k=width_k)
    
    # Check novelty: has this conjunction been seen before?
    is_novel = False
    for atom_conjunction in atoms:
        if atom_conjunction not in novelty_table:
            is_novel = True
            novelty_table.add(atom_conjunction)
            break
    
    if not is_novel:
        # Prune: no new information
        return "PRUNE"
    
    # Expand: generate all successors
    for action in legal_actions(current_state):
        next_state = transition(current_state, action)
        next_atoms = extract_atoms(next_state, k=width_k)
        
        # Enqueue if successor has novel atoms
        if any(atom not in novelty_table for atom in next_atoms):
            frontier.append(next_state)
    
    scratchpad.write("novelty_table", novelty_table)
    scratchpad.write("frontier", frontier)
    scratchpad.write("visited", visited)
    
    return action
```

**Training Data Format:**
```
Input:  [IMAGE or PDDL_TEXT] + scratchpad_state + width_k
Output: {
  "action": "pickup(a)",
  "novelty_check": {
    "k_atoms": ["(on a b)", "(on b c)"],
    "is_novel": true,
    "novel_atom": "(on a b)"
  },
  "scratchpad_update": {
    "novelty_table": ["(on a b)", "(clear c)", "..."],
    "frontier": ["state_1", "state_2"]
  }
}
```

**Why IW is essential:** IW introduces **structured exploration based on state novelty**, distinct from BFS's exhaustive search and FF's goal-directed search. It tests whether models can identify which parts of a state are "new" and worth exploring, a capability that may be differentially supported by language (abstract atoms) vs. vision (perceptual grouping).

#### 5.2.4 Algorithm 4: Graphplan with Proposition Layers

**Algorithm:** Layered proposition graph with mutex propagation (Blum & Furst, 1997).

**Simplification for Feasibility:**
We do not require full mutex extraction (which is NP-hard in general). Instead, we use **action mutex only** (two actions cannot execute simultaneously if they interfere on preconditions/effects).

**Layer Construction Protocol:**
```python
def graphplan_step(scratchpad, layer_id):
    current_layer = scratchpad.read(f"layer_{layer_id}")
    actions = scratchpad.read("available_actions")
    
    # Model selects applicable actions
    applicable = [a for a in actions if a.preconditions ⊆ current_layer]
    
    # Model identifies mutex pairs
    mutex_pairs = []
    for a1, a2 in combinations(applicable, 2):
        if interfere(a1, a2):
            mutex_pairs.append((a1, a2))
    
    next_propositions = current_layer ∪ {a.effects for a in applicable}
    
    scratchpad.write(f"layer_{layer_id+1}", next_propositions)
    scratchpad.write(f"mutex_{layer_id}", mutex_pairs)
    
    return "LAYER_COMPLETE"
```

**Training Data Format:**
```
Input:  PDDL_TEXT (required) + optional IMAGE + scratchpad_layers
Output: {
  "layer_update": {
    "propositions": ["(on a table)", "(clear b)", "(handempty)"],
    "actions": ["unstack(a,b)", "pickup(c)"],
    "mutex_pairs": [("unstack(a,b)", "pickup(c)")]
  },
  "extraction_plan": null
}
```

**Why Graphplan is essential:** Graphplan introduces **constraint-based reasoning over proposition layers**, fundamentally different from state-space search. It tests whether language (which provides the propositional vocabulary) is necessary for this algorithmic paradigm, as predicted by CRSH.

### 5.3 Frozen World Model Technical Specification

#### 5.3.1 Discrete Domain: Blocksworld (GNN/Transformer)

**Architecture:** Lightweight Graph Transformer (≤10M parameters)

**Input:** PDDL state as graph
- **Nodes:** Objects (blocks, table) with features $[type, position, clear\_status, in\_hand]$
- **Edges:** Relations $(on, above, clear, holding)$ with directional features

**Encoder:** 4-layer Graph Transformer with edge bias
```
h_v^(0) = Embedding(node_features_v)
h_e^(0) = Embedding(edge_features_e)

for l in 1..4:
    h_v^(l) = MHA(h_v^(l-1), h_v^(l-1), h_v^(l-1)) + h_v^(l-1)
    h_v^(l) = FFN(LayerNorm(h_v^(l))) + h_v^(l)
    
z_state = GlobalMeanPool(h_v^(4))
```

**Training:** Self-supervised next-state prediction on Blocksworld trajectories
$$\mathcal{L}_{WM} = \|z_{t+1} - \hat{z}_{t+1}\|_2^2$$

**Frozen Usage:** During planner training, $z_t$ is computed once and cached. The planner receives $z_t$ as a fixed vector of dimension 128.

#### 5.3.2 Continuous Domain: Push-T / Two-Room (LeWM)

**Architecture:** LeWM (15M parameters, JEPA-style)

**Input:** 64×64 RGB frames
**Encoder:** 4-layer CNN + projection head
**Predictor:** Latent dynamics model $f_\theta(z_t, a_t) \to z_{t+1}$

**Frozen Usage:** Same as Blocksworld—$z_t$ is pre-computed and cached.

#### 5.3.3 Interface Layer

Both world models output a **unified latent representation** $z_t \in \mathbb{R}^{128}$. The planner receives:
```
Input to Planner = [z_t; modality_specific_input; scratchpad_state]
```

### 5.4 Data Generation Pipeline

#### 5.4.1 Expert Trajectory Generation

For each algorithm, we generate expert demonstrations using classical planners:

| Algorithm | Expert Generator | Trajectory Length | Quantity |
|-----------|-----------------|-------------------|----------|
| BFS | FastDownward (optimal) | 3-9 steps | 10,000 |
| Fast Forward | FastDownward (lama-first) | 3-9 steps | 10,000 |
| Iterated Width | Custom Python (IW implementation) | 3-9 steps | 10,000 |
| Graphplan | FastDownward (planning graph) | Layer-wise | 5,000 |

**Blocksworld Task Distribution:**
- **Train:** 3-5 blocks, 3-step optimal plans
- **Test-Length:** 6-9 blocks, 6-9 step plans
- **Test-Comp:** Novel initial configurations (blocks in unseen towers), novel goal configurations

#### 5.4.2 SFT Data Format

Each training example is a **conversation**:
```
[
  {
    "role": "system",
    "content": "You are a planning agent executing [ALGORITHM]. You have access to [MODALITY_INPUTS] and a scratchpad."
  },
  {
    "role": "user",
    "content": {
      "world_model_latent": [128-dim vector],
      "modality_input": [IMAGE or PDDL_TEXT],
      "scratchpad": {...},
      "task": "Execute one step of [ALGORITHM]"
    }
  },
  {
    "role": "assistant",
    "content": {
      "action": "...",
      "algorithm_state_update": {...},
      "explanation": "..."
    }
  }
]
```

#### 5.4.3 Curriculum Strategy

| Phase | Data Mix | Epochs | Goal |
|-------|----------|--------|------|
| 1 | 100% 3-step tasks | 3 | Learn basic action validity |
| 2 | 70% 3-step + 30% 6-step | 5 | Learn horizon extension |
| 3 | 50% 3-step + 30% 6-step + 20% 9-step | 5 | Generalize to long horizon |
| 4 | 100% 9-step (fine-tuning only) | 2 | Polish long-horizon accuracy |

---

## 6. Cross-Task Generalization: Algorithmic Bias Transfer

### 6.1 The Transfer Hypothesis

We test whether planning biases transfer to non-planning reasoning tasks. The hypothesis is:

> **Algorithmic Bias Transfer (ABT):** A planner trained with resource $r$ on algorithm $a$ will exhibit characteristic failure modes when transferred to reasoning task $t$, where the failure mode is predicted by the algorithmic bias of $a$.

### 6.2 Target Tasks and Predicted Bias Transfer

| Source Training | Target Task | Input Format | Predicted Bias | Predicted Failure Mode |
|----------------|-------------|--------------|----------------|---------------------|
| **Vision-only + FF** | FOLIO (Logical Reasoning) | Natural language premises + conclusion | **Heuristic fixation** | Jumps to conclusion without checking all premises; high precision, low recall |
| **Language-only + Graphplan** | HumanEval (Code Debugging) | Buggy code + error message | **Constraint over-specification** | Over-constrains possible fixes; misses simple solutions due to mutex-like reasoning |
| **Tool-only + BFS** | GSM8K (Math Word Problems) | Text problem | **Exhaustive enumeration** | Tries all paths; slow but thorough; fails on time-constrained tasks |
| **VLA+Tool + IW** | FOLIO | Natural language | **Novelty-driven search** | Explores unusual interpretations; finds non-obvious conclusions but sometimes hallucinates |

### 6.3 Transfer Protocol

**Step 1:** Train planner on Blocksworld with configuration $(r, a)$.

**Step 2:** Freeze planner weights (no gradient updates).

**Step 3:** Evaluate zero-shot on target task with prompt:
```
You are solving a [REASONING_TASK]. 
Use the planning strategy you learned from Blocksworld.
[INPUT]
```

**Step 4:** Measure:
- **Accuracy:** Standard task metric (FOLIO: accuracy; HumanEval: pass@1; GSM8K: exact match)
- **Bias Consistency Score:** Correlation between planning failure mode and reasoning error type
  - Compute failure mode distribution on Blocksworld
  - Compute error type distribution on target task
  - BCS = $\text{cosine\_similarity}(\text{failure\_vector}, \text{error\_vector})$

---

## 7. Evaluation Metrics

### 7.1 Performance Metrics

| Metric | Definition | Target |
|--------|-----------|--------|
| Success Rate @ Horizon | % of tasks solved within step limit | $\geq 0.8$ for P0 |
| Sample Efficiency | Training steps to reach 0.8 success | Report curves |
| Length Generalization | Train 3-step $\to$ Test 6/9-step | $\Delta \leq 0.15$ drop |
| Compositional Generalization | Novel object arrangements | $\Delta \leq 0.20$ drop |

### 7.2 Process Metrics (Critical for CRSH)

| Metric | Definition | Why It Matters |
|--------|-----------|----------------|
| Convergence Curve Shape | Success vs. training steps | Sigmoidal = stable learning; oscillatory = resource mismatch |
| Effective Search Depth | Max depth reached before failure | Tests memory boundary |
| Tool Access Frequency | `read/write` calls per step | Tests reliance on external memory |
| Heuristic Deviation | $|h_{model}(s) - h_{optimal}(s)|$ | Tests FF heuristic quality |
| Novelty Accuracy | % of correct novelty detections in IW | Tests structured exploration capability |
| Mutex Accuracy | % of correct mutex pairs in Graphplan | Tests constraint reasoning |

### 7.3 Failure Mode Taxonomy

We define a **hierarchical error taxonomy** for all planning attempts:

**Level 1: Resource Failure**
- **Memory Overflow (MO):** Model forgets frontier states (BFS queue drifts, visited set shrinks)
- **Heuristic Fixation (HF):** Model repeatedly expands same state due to heuristic loop (FF)
- **Novelty Collapse (NC):** Model fails to identify novel atoms (IW prunes incorrectly)
- **Constraint Violation (CV):** Model proposes mutually exclusive actions (Graphplan)
- **Exploration Collapse (EC):** Model stops exploring; outputs "I don't know" or repeats last action

**Level 2: Algorithmic Failure**
- **FIFO Violation (BFS):** Queue updated LIFO or randomly
- **Relaxation Error (FF):** Delete-relaxation heuristic miscomputed; preconditions not ignored correctly
- **Width Miscalculation (IW):** k-atom extraction incorrect; novelty table corrupted
- **Layer Skipping (Graphplan):** Propositions added without prerequisite actions
- **Mutex Misclassification (Graphplan):** Mutex pairs identified when not truly interfering

**Level 3: Action Failure**
- **Syntax Error:** Unparseable output
- **Semantic Error:** Parseable but illegal action
- **Goal Misidentification:** Stops before goal reached or continues past goal

---

## 8. Experiment Priority Tiers

| Priority | Experiments | Must Complete? | Role in Story |
|----------|------------|----------------|---------------|
| **P0** | 4 Algorithm Families (BFS, FF, IW, Graphplan) × 4 Modalities × 3 seeds + Zero-Shot Diagnostic | **Yes** | Core CRSH test; learnability manifolds |
| **P1** | Cross-Task Transfer (FOLIO, HumanEval, GSM8K) | No | Algorithmic Bias Transfer |
| **P2** | Tool-Learned condition (autonomous read/write) | No | Appendix material |
| **P3** | Curriculum ablation, data ratio studies | No | Robustness checks |

---

## 9. Feasibility & Timeline

| Phase | Content | Duration | Deliverable |
|-------|---------|----------|-------------|
| **Week 1** | **Pre-Flight:** Zero-shot diagnostic on 4 algorithms × 4 modalities | 1 week | Go/No-Go decision matrix |
| Weeks 2-3 | Environment setup; world model training (Blocksworld GNN, LeWM fine-tuning) | 2 weeks | Frozen world models with <5% prediction error |
| Weeks 4-5 | Expert trajectory generation (FastDownward + custom IW/Graphplan) | 2 weeks | 35,000 trajectories with algorithmic annotations |
| Weeks 6-9 | Core P0 SFT experiments (4 algorithms × 4 modalities × 3 seeds) | 4 weeks | Convergence curves + failure taxonomy |
| Weeks 10-11 | Analysis: Pareto curves, CRSH boundary tests, BCS computation | 2 weeks | Statistical validation of hard boundaries |
| Weeks 12-13 | Paper writing | 2 weeks | Full draft with appendix |
| Buffer | Rebuttal preparation, code release | 2 weeks | Public repository |

**Total:** ~3.5 months (dropped P1 to focus on P0).

---

## 10. Risk Assessment & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Zero-shot diagnostic: all modalities fail all algorithms | Low | High | Switch to "algorithm discovery" framing; report which approximation each modality discovers |
| BFS with Tool-Template still fails due to queue management | Medium | High | Simplify to "Systematic Enumeration" (breadth-first without exact FIFO semantics); document as algorithmic approximation |
| Graphplan mutex propagation too complex | Medium | Medium | Use action-level mutex only (not proposition-level); reduce to "Layered Reachability" |
| IW novelty detection ambiguous in vision-only | Medium | Medium | Use language to define atoms; vision provides only perceptual grouping cues |
| VLA+Tool uniformly dominates (no Pareto frontier) | Medium | Medium | Shift to process-level analysis: convergence dynamics, failure modes, exploration patterns |
| Compute budget exceeded | Medium | High | P0 is 48 runs (4 algorithms × 4 modalities × 3 seeds); total manageable on 8×A100 cluster |

---

## 11. Pre-Flight Checklist (Execute Before Full Commitment)

| Check | Pass Criteria | Action if Fail |
|-------|--------------|----------------|
| Zero-shot: Text-only BFS/FF/IW/Graphplan | $\geq 30\%$ pass rate on any algorithm | If $< 10\%$: model lacks algorithmic knowledge; switch to discovery framing |
| Zero-shot: Vision-only any algorithm | $\leq 10\%$ pass rate | If $> 30\%$: vision unexpectedly strong; revise CRSH predictions |
| World model: Blocksworld GNN | MSE $< 0.05$ on next-state prediction | Retrain with more layers or switch to transformer |
| World model: LeWM on Push-T | MSE $< 0.10$ | Fine-tune LeWM on domain-specific frames |
| SFT data: 1000 BFS trajectories | Generated in $< 6$ hours | Optimize FastDownward pipeline |
| SFT pilot: 100 steps on BFS+Tool | Loss decreasing | Adjust learning rate or LoRA rank |

---

## 12. Contributions

1. **Conceptual:** Introduces the Computational Resource Substitution Hypothesis (CRSH) with formal hard/soft boundary definitions and pre-registered predictions.
2. **Methodological:** Proposes the zero-shot diagnostic protocol to decouple algorithmic knowledge from algorithmic affordance.
3. **Empirical:** Maps the first systematic learnability manifold for 4 distinct planning paradigms—systematic search (BFS), greedy heuristic search (FF), structured exploration (IW), and constraint reasoning (Graphplan)—across 4 modality configurations.
4. **Theoretical:** Demonstrates that algorithmic bias is a transferable cognitive trait across reasoning domains (Algorithmic Bias Transfer).
5. **Practical:** Provides actionable guidance for VLA system designers: which algorithms to use, which modalities to employ, and when external tools are non-negotiable.

---

## 13. One-Sentence Pitch

> **We do not ask whether LLMs can plan. We ask which algorithms their cognitive resources afford—and prove the answer is carved into the modality, not the model.**

---

## References

[1] BISON: Learning Bilevel Policies over Symbolic World Models for Long-Horizon Planning. arXiv:2605.15975, 2026.

[2] Hao S. et al. Reasoning via Planning (RAP). EMNLP 2023.

[3] Zhao W. et al. LLM-MCTS. NeurIPS 2023.

[4] Lu H. et al. SCOPE. arXiv:2512.09897, 2025.

[5] Sun J. et al. VLA-JEPA. arXiv:2602.10098, 2026.

[6] Dainese N. et al. ViPlan. arXiv:2505.13180, 2025.

[7] Maes L. et al. LeWorldModel. arXiv:2603.19312, 2026.

[8] Liu Y. et al. DELTA. 2024.

[9] Gibson, J. J. The Ecological Approach to Visual Perception. 1979.

[10] Carruthers, P. The Cognitive Functions of Language. 2002.

[11] Clark, A. & Chalmers, D. The Extended Mind. 1998.

[12] Luck, S. J. & Vogel, E. K. The capacity of visual working memory. Nature, 1997.

[13] Hoffmann, J. & Nebel, B. The FF Planning System: Fast Plan Generation Through Heuristic Search. JAIR, 2001.

[14] Lipovetzky, N. & Geffner, H. Width and Serialization in Classical Planning. ICAPS, 2012.

[15] Blum, A. & Furst, M. Fast Planning Through Planning Graph Analysis. IJCAI, 1997.

---

## Summary of Key Changes from Original Proposal

| Aspect | Original | Updated |
|--------|----------|---------|
| **Algorithms (P0)** | BFS, Greedy Best-First, A*, Graphplan | **BFS, Fast Forward, Iterated Width, Graphplan** |
| **Algorithm Families** | Blind, Heuristic, Graph (3 families) | **Systematic, Greedy Heuristic, Structured Exploration, Constraint (4 distinct paradigms)** |
| **Heuristic Search Representative** | Greedy + A* (two related variants) | **Fast Forward** (delete-relaxation, distinct from search) |
| **Novelty/Exploration** | Missing | **Iterated Width** (adds structured exploration via novelty) |
| **Theoretical Coverage** | State-space search only | **State-space (BFS, FF, IW) + Proposition-space (Graphplan)** |
| **Algorithmic Orthogonality** | Moderate (Greedy and A* share assumptions) | **High (each algorithm tests a fundamentally different planning philosophy)** |