(define (animation matched-rooms)
  (:predicate left :parameters (?x) :effect ((equal (?x x) 0)))
  (:predicate middle :parameters (?x) :effect ((equal (?x x) 120)))
  (:predicate right :parameters (?x) :effect ((equal (?x x) 240)))
  (:predicate at
    :parameters (?x)
    :custom agent
    :effect ((equal (agent x) (?x x)) (equal (agent y) 20)))
  (:visual place
    :type default
    :object (%place)
    :properties ((showName TRUE) (x 0) (y 0) (width 80) (height 80) (color BLUE) (depth 1)))
  (:visual agent
    :type custom
    :objects agent
    :properties ((showName TRUE) (x 0) (y 20) (width 40) (height 40) (color RED) (depth 2))))
