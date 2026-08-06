(define (problem cgas-source-eb14f31deebbc74183eb6547)
  (:domain blocksworld)
  (:objects a b c)
  (:init
  (clear b)
  (clear c)
  (holding a)
  (on-table b)
  (on-table c)
)
  (:goal
    (and (on a b)))
)
