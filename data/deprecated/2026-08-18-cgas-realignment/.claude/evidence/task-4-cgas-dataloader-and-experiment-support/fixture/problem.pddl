(define (problem bw-nontrivial-3)
  (:domain blocksworld)
  (:objects a b c)
  (:init
    (arm-empty)
    (clear a)
    (clear b)
    (clear c)
    (on-table a)
    (on-table b)
    (on-table c))
  (:goal
    (and (on a b)))
)
