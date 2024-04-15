pipeline {
    agent {
        node { label 'jenkinsworker00' }
    }
    
    environment {
        
        //DOCKER_HUB_CREDENTIALS = 'docker-hub-credentials'
        HARBOR_CREDENTIALS = 'harbor-paas-credentials'
        DOCKER_HUB_IMAGE_NAME = 'indigo-paas/orchestrator-dashboard'
        HARBOR_IMAGE_NAME = 'datacloud-middleware/orchestrator-dashboard'
    }
    
    stages {
        stage('Build and Tag Docker Image') {
            
            steps {
                script {
                    // Build Docker image
                    def dockerImage = docker.build("${DOCKER_HUB_IMAGE_NAME}:${env.BRANCH_NAME}", "-f docker/Dockerfile .")
                    
                    // Tag the image for Harbor
                    dockerImage.tag("${HARBOR_IMAGE_NAME}:${env.BRANCH_NAME}")
                    
                    // Export the Docker image object for later stages
                    env.DOCKER_IMAGE = dockerImage.id
                }
            }
        }
        
        stage('Push to Docker Hub and Harbor') {
            parallel {
                stage('Push to Docker Hub') {
                    steps {
                        script {
                            // Retrieve the Docker image object from the previous stage
                            def dockerImage = docker.image(env.DOCKER_IMAGE)
                            
                            // Login to Docker Hub
                            docker.withRegistry('https://index.docker.io/v1/', DOCKER_HUB_CREDENTIALS) {
                                // Push the Docker image to Docker Hub
                                dockerImage.push()
                            }
                        }
                    }
                }
                
                stage('Push to Harbor') {
                    steps {
                        script {
                            // Retrieve the Docker image object from the previous stage
                            def dockerImage = docker.image(env.DOCKER_IMAGE)
                            
                            // Login to Harbor
                            docker.withRegistry('https://harbor.cloud.infn.it', HARBOR_CREDENTIALS) {
                                // Push the Docker image to Harbor
                                dockerImage.push()
                            }
                        }
                    }
                }
            }
        }
    }
    
    post {
        success {
            echo 'Docker image build and push successful!'
        }
        failure {
            echo 'Docker image build and push failed!'
        }
    }
}

