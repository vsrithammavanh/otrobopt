from openturns import *
from openturns.viewer import *
from math import *

class LinearCombinationFunction(OpenTURNSPythonFunction):
    def __init__(self, coll, weights):
        super(LinearCombinationFunction, self).__init__(coll[0].getInputDimension(), coll[0].getOutputDimension())
        self.coll_ = coll
        self.weights_ = weights

    def _exec(self, X):
        result = self.coll_[0](X) * self.weights_[0]
        for i in range(1, len(self.coll_)):
            result += self.coll_[i](X) * self.weights_[i]
        return result
    
##################################################################
# Here we define the non-robust constrained optimization problem #
##################################################################

# This is calligraphic J, the non-robust objective function
calJ = NumericalMathFunction(["x1", "x2"], ["15.0 * (x1^2 + x2^2) - 100.0 * exp(-5. * ((x1 + 1.6)^2+(x2 + 1.6)^2))"])

# This is calligraphic G, the non-robust inequality constraints function
calG = NumericalMathFunction(["x1", "x2"], ["(x1 - 0.5)^2 + x2^2 - 4.0", "(x1 + 0.5)^2 + x2^2 - 4.0"])

######################################################
# Here we define the parametric optimization problem #
######################################################

# This is the perturbation function
noise = NumericalMathFunction(["x1", "x2", "xi1", "xi2"], ["x1 + xi1", "x2 + xi2"])

# This is capital J: J(x,xi) = calJ(x+xi), the parametric objective function
J = NumericalMathFunction(calJ, noise)

# This is g, the parametric constraints
g = NumericalMathFunction(calG, noise)

##################################################
# Here we define the robust optimization problem #
##################################################

# The robustness measure is the expectation of J

# This is the factory of rhoJ_N, the robust objective function in its discretized form
def discretizeExpectation(J, sampleXi):
    size = sampleXi.getSize()
    functionCollection = list()
    # For each value of the parameter
    for i in range(size):
        # Build a copy of J as a parametric function (the third and fourth arguments of J are the parameters)
        currentContributor = NumericalMathFunction(J, [2, 3])
        # Set the value of the parameter
        currentContributor.setParameter(NumericalPointWithDescription(sampleXi[i]))
        # Augment the collection
        functionCollection.append(currentContributor)
    # The resulting discretized expectation is the linear combination of all the parametric functions with a uniform weight of 1/size
    # Here we have a bug when using the combination: AnalyticalNumericalMathFunction+several clones using ParametricFunction into LinearCombinationFunction, due to a race condition in the initialization of the underlying AnalyticalFunction and the parallel evaluation of the LinearCombination. It is solved by reimplementing a sequential evaluation in Python.
    #return NumericalMathFunction(functionCollection, [1.0 / size]*size)
    return NumericalMathFunction(LinearCombinationFunction(functionCollection, [1.0 / size]*size))

# The reliability measure is the joint chance constraint of level alpha
def discretizeJointChance(g, sampleXi, alpha):
    size = sampleXi.getSize()
    functionCollection = list()
    test = NumericalMathFunction(["y1", "y2"], ["(y1 >= 0.0) && (y2 >= 0.0)"])
    # For each value of the parameter
    for i in range(size):
        # Build a copy of g as a parametric function (the third and fourth arguments of g are the parameters)
        currentContributor = NumericalMathFunction(g, [2, 3])
        # Set the value of the parameter
        currentContributor.setParameter(NumericalPointWithDescription(sampleXi[i]))
        # Augment the collection
        functionCollection.append(NumericalMathFunction(test, currentContributor))
    # The resulting discretized probability is the linear combination of all the test functions with a uniform weight of 1/size
    # Here we have a bug when using the combination: AnalyticalNumericalMathFunction+several clones using ParametricFunction into LinearCombinationFunction, due to a race condition in the initialization of the underlying AnalyticalFunction and the parallel evaluation of the LinearCombination. It is solved by reimplementing a sequential evaluation in Python.
    # return NumericalMathFunction(NumericalMathFunction("t", str(alpha) + " - t"), NumericalMathFunction(functionCollection, [1.0 / size]*size))
    return NumericalMathFunction(NumericalMathFunction("t", str(alpha) + " - t"), NumericalMathFunction(LinearCombinationFunction(functionCollection, [1.0 / size]*size)))

################################################################################
# Here we solve the robust optimization problem using the sequential algorithm #
################################################################################

class sequentialRobustOptimisationSolver:
    def __init__(self, J, g, distributionXi, alpha, bounds, solver, N0, maximumIteration, robustIteration, initialSearch = 100, epsilon = 1e-10, drawFlag = False, verbose = False, directory = "."):
        self.J_ = J
        self.g_ = g
        self.distributionXi_ = distributionXi
        self.alpha_ = alpha
        self.bounds_ = bounds
        self.solver_ = solver
        self.N0_ = N0
        self.maximumIteration_ = maximumIteration
        self.robustIteration_ = robustIteration
        self.initialSearch_ = initialSearch
        self.epsilon_ = epsilon
        self.drawFlag_ = drawFlag
        self.verbose_ = verbose
        self.path_ = NumericalSample(0, J.getInputDimension() - distributionXi.getDimension())
        self.directory_ = directory
        
    def solve(self):
        self.path_ = NumericalSample(0, self.J_.getInputDimension() - self.distributionXi_.getDimension())
        currentSampleXi = NumericalSample(0, distributionXi.getDimension())
        currentN = self.N0_
        for iteration in range(self.robustIteration_):
            if self.verbose_:
                print "start iteration", iteration
            # Draw an additional set of random parameters
            if self.verbose_:
                print "sample xi"
            currentSampleXi.add(self.distributionXi_.getSample(currentN))
            currentN = currentSampleXi.getSize()
            print "Sample size=", currentN
            # Discretize the parametric optimization problem accordingly
            if self.verbose_:
               print "discretize rhoJ"
            rhoJ = discretizeExpectation(self.J_, currentSampleXi)
            if self.drawFlag_:
                print "draw rhoJ"
                ResourceMap.SetAsUnsignedInteger("Contour-DefaultLevelsNumber", 10)
                gRhoJ = rhoJ.draw(self.bounds_.getLowerBound(), self.bounds_.getUpperBound(), [100]*2)
            if self.verbose_:
                print "discretize pG"
            pG = discretizeJointChance(self.g_, currentSampleXi, self.alpha_)
            if self.drawFlag_:
                print "draw pG"
                ResourceMap.SetAsUnsignedInteger("Contour-DefaultLevelsNumber", 1)
                gPG = pG.draw(self.bounds_.getLowerBound(), self.bounds_.getUpperBound(), [200]*2)
                c = gPG.getDrawable(0)
                c.setLevels([alpha])
                c.setLabels([str(alpha)])
                gPG.setDrawable(c, 0)
            # Create the resulting optimization problem
            if self.verbose_:
                print "create problem"
            problem = OptimizationProblem()
            problem.setObjective(rhoJ)
            problem.setInequalityConstraint(pG)
            problem.setBounds(self.bounds_)
            problem.setMinimization(True)
            if self.verbose_:
                print "adapt the solver"
            self.solver_.setProblem(problem)
            self.solver_.setMaximumIterationNumber(self.maximumIteration_)
            # Here we have to push a little bit on the optimization epsilon
            currentEpsilon = 1.0e-2 / sqrt(currentN)
            self.solver_.setMaximumAbsoluteError(currentEpsilon)
            self.solver_.setMaximumRelativeError(currentEpsilon)
            self.solver_.setMaximumResidualError(currentEpsilon)
            self.solver_.setMaximumConstraintError(currentEpsilon)
            self.solver_.setVerbose(True)
            # Solve the current discretized robust optimization problem
            if self.verbose_:
                print "solve the problem"
            # For the first iteration, do multi-start optimization to (try) to find a global optimum
            if iteration > 0:
                self.solver_.setStartingPoint(currentPoint)
                self.solver_.run()
                newPoint = self.solver_.getResult().getOptimalPoint()
                bestValue = self.solver_.getResult().getOptimalValue()[0]
            else:
                startingPoints = LHSExperiment(ComposedDistribution([Uniform(self.bounds_.getLowerBound()[i], self.bounds_.getUpperBound()[i]) for i in range(self.bounds_.getDimension())]), self.initialSearch_).generate()
                bestValue = SpecFunc.MaxNumericalScalar
                newPoint = startingPoints[0]
                for i in range(startingPoints.getSize()):
                    if i % (startingPoints.getSize() / 100) == 0:
                        print i, "/", startingPoints.getSize()-1
                    startingPoint = startingPoints[i]
                    self.solver_.setStartingPoint(startingPoint)
                    self.solver_.run()
                    # Extract the optimal point
                    result = self.solver_.getResult()
                    currentValue = result.getOptimalValue()[0]
                    if currentValue < bestValue:
                        bestValue = currentValue
                        newPoint = result.getOptimalPoint()
                        print "Best initial point so far=", newPoint, "value=", bestValue
            if self.verbose_:
                print "current optimum=", newPoint
            self.path_.add(newPoint)
            print "path=\n", self.path_
            if self.drawFlag_:
                g = Graph(gRhoJ)
                g.add(gPG)
                c = Curve(self.path_)
                c.setLineStyle("dashed")
                c.setColor("red")
                g.add(c)
                c = Cloud(self.path_)
                c.setPointStyle("fcircle")
                c.setColor("red")
                g.add(c)
                c = Cloud([newPoint])
                c.setPointStyle("star")
                c.setColor("cyan")
                g.add(c)
                g.setTitle("sigma=" + str(sigma_xi) + ", rhoJ_N, pG_N for N=" + str(currentN) + "\nx^*=" + str(newPoint) + ", rhoJ^*=" + str(bestValue))
                print "draw convergence"
                g.draw(self.directory_ + "/convergence_iteration_" + str(iteration) + "_N_" + str(currentN).zfill(2) + "_sigma_" + str(sigma_xi).zfill(4) + ".png", 800, 820)
            if iteration > 0 and ((newPoint - currentPoint).norm() < self.epsilon_ or currentEpsilon < self.epsilon_):
                break
            currentPoint = newPoint
        return newPoint

    def getPath(self):
        return self.path_

all_sigma = [0.1, 0.2, 0.3, 0.4, 0.5]
for i in range(len(all_sigma)):
    # Probabilistic model for the uncertainties
    sigma_xi = all_sigma[i]
    directory = "sigma_" + str(sigma_xi)
    distributionXi = Normal([0.0]*2, [sigma_xi]*2, IdentityMatrix(2))

    # Parameters for the robust optimization problem
    bounds = Interval([-3.0]*2, [3.0]*2)
    alpha = 0.9

    # Parameters for the robust optimization solver
    N0 = 2
    localIterations = 100
    robustIterations = 11
    initialSearch = 1000
    solver = SLSQP()
    epsilon = 1.0e-6
    drawFlag = True
    verboseFlag = True

    # Robust optimization solver
    # parameters: J, g, distributionXi, alpha, bounds, solver, N0, maximumIteration, robustIteration, initialSearch = 100, epsilon = 1e-10, drawFlag = False, verbose = False
    robustAlgorithm = sequentialRobustOptimisationSolver(J, g, distributionXi, alpha, bounds, solver, N0, localIterations, robustIterations, initialSearch, epsilon, drawFlag, verboseFlag)
    solution = robustAlgorithm.solve()

    print "solution=", solution
