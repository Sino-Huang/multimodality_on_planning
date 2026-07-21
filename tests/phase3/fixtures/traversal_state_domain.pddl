(define (domain traversal-state-fixture)
  (:requirements :strips :typing)
  (:types place)
  (:predicates (at ?place - place) (connected ?from - place ?to - place))
  (:action move
    :parameters (?from - place ?to - place)
    :precondition (and (at ?from) (connected ?from ?to))
    :effect (and (not (at ?from)) (at ?to)))
)
