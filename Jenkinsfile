pipeline {
    agent any

    environment {
        DOCKERHUB_CREDENTIALS = credentials('dockerhub-credentials')
        KUBECONFIG            = credentials('k3d-kubeconfig')

        IMAGE_NAME            = 'sergiocosu/inventory-service'
        IMAGE_TAG             = "${env.BUILD_NUMBER}"
        SOLUTION_PATH         = 'Microservicios_y_Docker/InventoryService.sln'
        DOCKER_BUILD_CONTEXT  = 'Microservicios_y_Docker'
    }

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build & Test (.NET)') {
            agent {
                docker {
                    image 'mcr.microsoft.com/dotnet/sdk:8.0'
                    args '-u root:root'
                    reuseNode true
                }
            }
            steps {
                sh "dotnet restore ${SOLUTION_PATH}"
                sh "dotnet build ${SOLUTION_PATH} --no-restore --configuration Release"
                sh "dotnet test ${SOLUTION_PATH} --no-build --configuration Release --verbosity normal"
            }
        }

        stage('Docker Build') {
            steps {
                sh "docker build -t ${IMAGE_NAME}:${IMAGE_TAG} -t ${IMAGE_NAME}:latest ${DOCKER_BUILD_CONTEXT}"
            }
        }

        stage('Docker Push') {
            steps {
                sh 'echo "$DOCKERHUB_CREDENTIALS_PSW" | docker login -u "$DOCKERHUB_CREDENTIALS_USR" --password-stdin'
                sh "docker push ${IMAGE_NAME}:${IMAGE_TAG}"
                sh "docker push ${IMAGE_NAME}:latest"
            }
        }

        stage('Deploy to k3d') {
            steps {
                sh """
                    helm upgrade --install inventory ./inventory-chart \
                      --set image.repository=${IMAGE_NAME} \
                      --set image.tag=${IMAGE_TAG} \
                      --wait --timeout 2m
                """
            }
        }
    }

    post {
        always {
            sh 'docker logout || true'
        }
        success {
            echo "Despliegue exitoso: ${IMAGE_NAME}:${IMAGE_TAG}"
        }
        failure {
            echo 'El pipeline de CD falló. Revisa el log de la etapa correspondiente.'
        }
    }
}
