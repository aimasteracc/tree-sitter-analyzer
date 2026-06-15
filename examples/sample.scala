package examples

import scala.util.Try

final case class Job(name: String, retries: Int)

trait Runner {
  def run(job: Job): Either[String, Int]
}

object SampleApp extends Runner {
  private val defaultJob = Job("analyze", 3)

  override def run(job: Job): Either[String, Int] = {
    if (job.retries < 0) Left("invalid retries")
    else Right(job.retries + 1)
  }

  def main(args: Array[String]): Unit = {
    val selected = args.headOption.map(name => defaultJob.copy(name = name)).getOrElse(defaultJob)
    val result = Try(run(selected)).toEither.left.map(_.getMessage).flatten
    println(result)
  }
}
