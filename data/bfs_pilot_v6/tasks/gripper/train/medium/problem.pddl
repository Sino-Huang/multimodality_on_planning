


(define (problem gripper-3)
(:domain gripper-strips)
(:objects  roomb rooma left right ball2 ball3 ball1 )
(:init
(room roomb)
(room rooma)
(gripper left)
(gripper right)
(ball ball2)
(ball ball3)
(ball ball1)
(free left)
(free right)
(at ball2 roomb)
(at ball3 roomb)
(at ball1 roomb)
(at-robby roomb)
)
(:goal
(and
(at ball2 rooma)
(at ball3 rooma)
(at ball1 rooma)
)
)
)


