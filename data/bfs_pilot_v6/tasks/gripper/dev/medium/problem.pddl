


(define (problem gripper-3)
(:domain gripper-strips)
(:objects  rooma roomb right left ball2 ball3 ball1 )
(:init
(room rooma)
(room roomb)
(gripper right)
(gripper left)
(ball ball2)
(ball ball3)
(ball ball1)
(free right)
(free left)
(at ball2 rooma)
(at ball3 rooma)
(at ball1 rooma)
(at-robby rooma)
)
(:goal
(and
(at ball2 roomb)
(at ball3 roomb)
(at ball1 roomb)
)
)
)


