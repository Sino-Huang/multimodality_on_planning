


(define (problem gripper-3)
(:domain gripper-strips)
(:objects  rooma roomb right left ball3 ball1 ball2 )
(:init
(room rooma)
(room roomb)
(gripper right)
(gripper left)
(ball ball3)
(ball ball1)
(ball ball2)
(free right)
(free left)
(at ball3 rooma)
(at ball1 rooma)
(at ball2 rooma)
(at-robby rooma)
)
(:goal
(and
(at ball3 roomb)
(at ball1 roomb)
(at ball2 roomb)
)
)
)


