


(define (problem gripper-5)
(:domain gripper-strips)
(:objects  rooma roomb left right ball2 ball3 ball4 ball5 ball1 )
(:init
(room rooma)
(room roomb)
(gripper left)
(gripper right)
(ball ball2)
(ball ball3)
(ball ball4)
(ball ball5)
(ball ball1)
(free left)
(free right)
(at ball2 rooma)
(at ball3 rooma)
(at ball4 rooma)
(at ball5 rooma)
(at ball1 rooma)
(at-robby rooma)
)
(:goal
(and
(at ball2 roomb)
(at ball3 roomb)
(at ball4 roomb)
(at ball5 roomb)
(at ball1 roomb)
)
)
)


