(define (domain matched-rooms)
  (:requirements :strips)
  (:predicates (at ?x) (link ?x ?y) (left ?x) (middle ?x) (right ?x))
  (:action move
    :parameters (?x ?y)
    :precondition (and (at ?x) (link ?x ?y))
    :effect (and (not (at ?x)) (at ?y))))
