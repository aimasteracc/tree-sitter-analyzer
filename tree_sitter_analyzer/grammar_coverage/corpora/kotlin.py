"""Built-in Kotlin corpus for grammar coverage auto-discovery."""

CORPUS: str = """\
package com.example

import kotlinx.coroutines.*

const val MAX_RETRIES = 3

data class Point(val x: Double, val y: Double) {
    operator fun plus(other: Point) = Point(x + other.x, y + other.y)
}

sealed class Result<out T> {
    data class Success<T>(val value: T) : Result<T>()
    data class Error(val message: String) : Result<Nothing>()
}

interface Repository<T> {
    suspend fun find(id: Int): T?
    suspend fun findAll(): List<T>
}

enum class Status(val label: String) {
    ACTIVE("active"), INACTIVE("inactive"), PENDING("pending");
    fun isActive() = this == ACTIVE
}

annotation class Service(val name: String = "")

object Singleton { val value = 42 }

@Service(name = "UserService")
class UserService : Repository<User> {
    private val users = mutableListOf<User>()
    val (first, second) = Pair(1, 2)

    override suspend fun find(id: Int): User? = users.firstOrNull { it.id == id }
    override suspend fun findAll(): List<User> = users.toList()

    fun controlFlow(x: Int) {
        if (x > 0) { } else if (x < 0) { } else { }
        for (i in 0..x) { if (i == 3) continue; if (i == 7) break }
        while (x > 0) { }
        do { } while (false)
        when (x) { 1 -> println("one"); else -> println("other") }
    }
}

data class User(val id: Int, val name: String, val email: String? = null)

typealias UserList = List<User>
typealias Predicate<T> = (T) -> Boolean

suspend fun main() {
    val service = UserService()
    coroutineScope {
        launch { service.findAll() }
        async { service.findAll() }.await()
    }
}
"""
