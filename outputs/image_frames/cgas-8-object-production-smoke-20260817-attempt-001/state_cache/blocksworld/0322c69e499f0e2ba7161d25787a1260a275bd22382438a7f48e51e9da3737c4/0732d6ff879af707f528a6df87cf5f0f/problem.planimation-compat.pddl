

(define (problem 0322c69e499f0e2ba7161d25787a1260a275bd22382438a7f48e51e9da3737c4-00014e0bdfd513580c65f03b94e5c0a1)
(:domain blocksworld-4ops)
(:objects b1 b2 b3 b4 b5 b6 b7 b8 )
(:init
  (arm-empty)
  (clear b4)
  (clear b5)
  (clear b8)
  (on b2 b1)
  (on b3 b2)
  (on b4 b3)
  (on b5 b6)
  (on b8 b7)
  (on-table b1)
  (on-table b6)
  (on-table b7)
)
(:goal
(and
(on b2 b1)
(on b3 b2)
(on b5 b4)
(on b6 b5)
(on b8 b7))
)
)


